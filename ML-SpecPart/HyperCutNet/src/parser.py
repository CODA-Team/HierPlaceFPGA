import dgl
import torch as th
import os
import random
import hashlib
import re
import numpy as np
from collections import defaultdict
from scipy import sparse as sp

import networkx as nx
try:
    # optional dependency; if missing, node2vec features will be skipped
    from node2vec import Node2Vec
except ImportError:
    Node2Vec = None


NODE2VEC_DIM = 32
NODE2VEC_WALK_LENGTH = 50
NODE2VEC_NUM_WALKS = 10
NODE2VEC_P = 1.0
NODE2VEC_Q = 1.0
NODE2VEC_WORKERS = 4

# Skip nets larger than this when building pin-pin graph (avoids O(n^2) blowup for
# huge nets like 98k-pin clock nets; same idea as HUGE_NET_THRESHOLD for net overlaps)
PIN_PIN_MAX_NET_SIZE = 200

# When using heterogeneous (pin-net) analogs for pin structural features, we still
# need a compute cap for iterating over pins inside huge nets. This avoids
# pathological per-pin feature costs while removing the pin-pin clique blowup.
HETERO_PIN_FEAT_SAMPLE_PINS_PER_NET = 5000

# In-process cache for node2vec embeddings keyed by graph structure.
_NODE2VEC_CACHE = {}


def _node2vec_cache_path(graph_path, structure_key):
    """
    Build disk cache path for node2vec embedding.
    Cache root prefers:
      1) $HYPERCUTNET_N2V_CACHE_DIR if set
      2) a ``node2vec_disk_cache`` directory next to this source tree
    """
    env_dir = os.environ.get("HYPERCUTNET_N2V_CACHE_DIR", "").strip()
    if env_dir:
        cache_root = env_dir
    else:
        hypercutnet_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cache_root = os.path.join(hypercutnet_root, "node2vec_disk_cache")
    os.makedirs(cache_root, exist_ok=True)
    return os.path.join(cache_root, f"node2vec_{structure_key}.pt")


def _hash_graph_structure(num_pins, p2n_src, p2n_dst):
    """
    对 pin-net 连接结构做稳定哈希，作为 node2vec cache key。
    只要结构一致（即使路径不同、label 不同），就会命中同一个 key。
    """
    if len(p2n_src) != len(p2n_dst):
        raise ValueError("p2n_src and p2n_dst length mismatch")

    if len(p2n_src) == 0:
        pair_bytes = b""
    else:
        pairs = np.column_stack(
            (
                np.asarray(p2n_src, dtype=np.int32),
                np.asarray(p2n_dst, dtype=np.int32),
            )
        )
        order = np.lexsort((pairs[:, 0], pairs[:, 1]))
        pair_bytes = pairs[order].tobytes()

    h = hashlib.blake2b(digest_size=16)
    h.update(np.int32(num_pins).tobytes())
    h.update(np.int32(len(p2n_src)).tobytes())
    h.update(pair_bytes)
    # include node2vec config so changed hyper-params won't reuse stale cache
    h.update(
        (
            f"{NODE2VEC_DIM}|{NODE2VEC_WALK_LENGTH}|{NODE2VEC_NUM_WALKS}|"
            f"{NODE2VEC_P}|{NODE2VEC_Q}"
        ).encode()
    )
    return h.hexdigest()


def _build_pin_pin_graph(num_pins, p2n_src, p2n_dst):
    """构建 pin-pin 无向图（同一 Net 下的 Pin 两两相连），用于聚类系数与 2 阶度。
    超大 net (pin 数 > PIN_PIN_MAX_NET_SIZE) 会被跳过，避免 O(n^2) 爆炸。"""
    G = nx.Graph()
    G.add_nodes_from(range(num_pins))
    net_to_pins = defaultdict(list)
    for pin_idx, net_idx in zip(p2n_src, p2n_dst):
        net_to_pins[net_idx].append(pin_idx)
    for pins in net_to_pins.values():
        if len(pins) < 2:
            continue
        if len(pins) > PIN_PIN_MAX_NET_SIZE:
            continue  # skip huge nets to avoid O(n^2) edges (e.g. 98k-pin net -> 4.8B edges)
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                u, v = pins[i], pins[j]
                if not G.has_edge(u, v):
                    G.add_edge(u, v)
    return G


def _compute_pin_structural_feats(num_pins, p2n_src, p2n_dst):
    """
    计算每个 Pin 的聚类系数和 2 阶度，返回形状 (num_pins, 2) 的张量。
    - 2nd-order degree: 邻居度数和
    """
    G = _build_pin_pin_graph(num_pins, p2n_src, p2n_dst)
    clustering = nx.clustering(G)
    deg = dict(G.degree())
    second_order_deg = []
    for nid in range(num_pins):
        c = clustering.get(nid, 0.0)
        so = sum(deg.get(v, 0) for v in G.neighbors(nid))
        second_order_deg.append([float(c), float(so)])
    return th.tensor(second_order_deg, dtype=th.float32)


def _compute_pin_structural_feats_hetero(
    num_pins,
    num_nets,
    pin_to_nets,
    net_to_pins,
    sample_pins_per_net=HETERO_PIN_FEAT_SAMPLE_PINS_PER_NET,
):
    """
    Compute heterogeneous analogs of:
      - clustering coefficient
      - 2nd-order degree

    We use the pin-net bipartite graph (pins <-> nets):
      - clustering: count 4-cycles through the pin (two distinct incident nets
        sharing another pin) using counts of "common nets" per neighbor pin.
      - 2nd-order degree: sum over distinct neighbor pins (reachable via sharing
        >=1 net) of (pin_net_degree(neighbor)-1).

    To control runtime for huge nets, when a net contains more than
    `sample_pins_per_net` pins, we iterate over a deterministic prefix of pins.
    """
    pin_net_deg = [len(pin_to_nets.get(v, [])) for v in range(num_pins)]
    feats = []

    for v in range(num_pins):
        nets_v = pin_to_nets.get(v, [])
        d = len(nets_v)
        if d < 2:
            feats.append([0.0, 0.0])
            continue

        # For each other pin u, count how many common nets it shares with v.
        common_counts = {}

        for e in nets_v:
            pins_e = net_to_pins.get(e, [])
            if len(pins_e) > sample_pins_per_net:
                pins_iter = pins_e[:sample_pins_per_net]
            else:
                pins_iter = pins_e
            for u in pins_iter:
                if u == v:
                    continue
                # multiplicity = number of common nets
                common_counts[u] = common_counts.get(u, 0) + 1

        # clustering numerator = sum_u C(common_counts[u], 2)
        numer = 0.0
        for c in common_counts.values():
            if c >= 2:
                numer += (c * (c - 1)) / 2.0

        denom = (d * (d - 1)) / 2.0
        clustering = (numer / denom) if denom > 0 else 0.0

        # 2nd-order analog: sum over distinct neighbor pins of (deg(u)-1)
        second_order = 0.0
        for u in common_counts.keys():
            second_order += max(0, pin_net_deg[u] - 1)

        feats.append([float(clustering), float(second_order)])

    return th.tensor(feats, dtype=th.float32)


def _compute_pin_pagerank(num_pins, p2n_src, p2n_dst):
    """
    在 pin-pin 图上计算 PageRank，返回形状 (num_pins, 1) 的张量。
    """
    G = _build_pin_pin_graph(num_pins, p2n_src, p2n_dst)
    if G.number_of_edges() == 0:
        return th.zeros((num_pins, 1), dtype=th.float32)
    pr = nx.pagerank(G)
    vals = [float(pr.get(nid, 0.0)) for nid in range(num_pins)]
    return th.tensor(vals, dtype=th.float32).reshape(-1, 1)


def _compute_pin_pagerank_hetero(
    num_pins,
    num_nets,
    pin_to_nets,
    net_to_pins,
    damping=0.85,
    max_iter=50,
    tol=1e-6,
):
    """
    PageRank on the heterogeneous bipartite graph (pins <-> nets).
    Implemented via power iteration over pin->net->pin random walks to avoid
    building an explicit pin-pin clique.
    """
    n_total = num_pins + num_nets
    pr = np.ones(n_total, dtype=np.float64) / n_total

    deg_pins = np.zeros(num_pins, dtype=np.float64)
    for v in range(num_pins):
        deg_pins[v] = float(len(pin_to_nets.get(v, [])))
    deg_nets = np.zeros(num_nets, dtype=np.float64)
    for e in range(num_nets):
        deg_nets[e] = float(len(net_to_pins.get(e, [])))

    for _ in range(max_iter):
        new_pr = np.zeros(n_total, dtype=np.float64)

        # pin -> net
        for v in range(num_pins):
            dv = deg_pins[v]
            if dv <= 0.0:
                continue
            share = pr[v] / dv
            for e in pin_to_nets.get(v, []):
                new_pr[num_pins + e] += share

        # net -> pin
        for e in range(num_nets):
            de = deg_nets[e]
            if de <= 0.0:
                continue
            share = pr[num_pins + e] / de
            for v in net_to_pins.get(e, []):
                new_pr[v] += share

        # damping + teleport
        new_pr = damping * new_pr + (1.0 - damping) / n_total
        s = new_pr.sum()
        if s > 0:
            new_pr /= s

        if np.linalg.norm(new_pr - pr, ord=1) < tol:
            pr = new_pr
            break
        pr = new_pr

    pin_pr = pr[:num_pins].astype(np.float32)
    return th.tensor(pin_pr, dtype=th.float32).reshape(-1, 1)


def _compute_pin_node2vec(num_pins, p2n_src, p2n_dst, graph_path=None, use_disk_cache=False):
    """
    在 Pin 层面构建无向图（同一 Net 下的 Pin 两两相连），
    然后对该图运行 node2vec，返回形状为 (num_pins, NODE2VEC_DIM) 的张量。
    如果未安装 node2vec 或无有效边，则返回 None。
    使用图结构哈希派生确定性 seed；同构图（仅 label 不同）可复用 embedding。
    """
    if Node2Vec is None:
        print("node2vec package not found, skip node2vec features.")
        return None

    structure_key = _hash_graph_structure(num_pins, p2n_src, p2n_dst)
    cached = _NODE2VEC_CACHE.get(structure_key)
    if cached is not None:
        print(f"Reusing cached node2vec embedding (key={structure_key[:8]}).")
        return cached.clone()

    disk_cache_path = None
    if use_disk_cache:
        disk_cache_path = _node2vec_cache_path(graph_path, structure_key)
        if os.path.exists(disk_cache_path):
            try:
                emb_tensor = th.load(disk_cache_path, map_location="cpu")
                if isinstance(emb_tensor, th.Tensor) and emb_tensor.shape == (num_pins, NODE2VEC_DIM):
                    _NODE2VEC_CACHE[structure_key] = emb_tensor.clone()
                    print(f"Loaded node2vec disk cache (key={structure_key[:8]}).")
                    return emb_tensor.clone()
                print(f"Ignore invalid node2vec disk cache shape: {disk_cache_path}")
            except Exception as e:
                print(f"Failed to load node2vec disk cache {disk_cache_path}: {e}")

    # 确定性 seed：由图结构哈希派生，而非 graph_path
    seed = int(structure_key[:8], 16)
    random.seed(seed)
    np.random.seed(seed)

    G = _build_pin_pin_graph(num_pins, p2n_src, p2n_dst)
    if G.number_of_edges() == 0:
        print("Pin graph has no edges, skip node2vec features.")
        return None

    node2vec = Node2Vec(
        G,
        dimensions=NODE2VEC_DIM,
        walk_length=NODE2VEC_WALK_LENGTH,
        num_walks=NODE2VEC_NUM_WALKS,
        p=NODE2VEC_P,
        q=NODE2VEC_Q,
        workers=1,  # required for reproducibility
        seed=seed,
    )
    model = node2vec.fit(window=10, min_count=1, batch_words=128, seed=seed, workers=1)

    emb = np.zeros((num_pins, NODE2VEC_DIM), dtype=np.float32)
    for nid in G.nodes():
        key = str(nid)
        emb[nid] = model.wv[key]

    emb_tensor = th.from_numpy(emb)
    _NODE2VEC_CACHE[structure_key] = emb_tensor.clone()
    if use_disk_cache and disk_cache_path is not None:
        try:
            th.save(emb_tensor, disk_cache_path)
            print(f"Saved node2vec disk cache (key={structure_key[:8]}).")
        except Exception as e:
            print(f"Failed to save node2vec disk cache {disk_cache_path}: {e}")
    print(f"Cached node2vec embedding (key={structure_key[:8]}).")
    return emb_tensor


def _compute_net_overlaps_sparse(num_pins, num_nets, p2n_src, p2n_dst):
    """
    Compute exact net-net overlap counts with sparse incidence multiplication.
    C = B^T * B, where B is pin-net incidence.
    """
    if len(p2n_src) == 0:
        return [], [], []

    rows = np.asarray(p2n_src, dtype=np.int32)  # pin idx
    cols = np.asarray(p2n_dst, dtype=np.int32)  # net idx
    vals = np.ones(rows.shape[0], dtype=np.int32)

    incidence = sp.csr_matrix((vals, (rows, cols)), shape=(num_pins, num_nets), dtype=np.int32)
    overlap = (incidence.T @ incidence).tocoo()

    r = overlap.row
    c = overlap.col
    w = overlap.data.astype(np.int32)

    # Remove self-overlaps and keep strictly positive overlaps.
    mask = (r != c) & (w > 0)
    r = r[mask]
    c = c[mask]
    w = w[mask]

    return r.tolist(), c.tolist(), w.tolist()


def _prune_net_overlap_edges(n2n_src, n2n_dst, n2n_weight, topk=0, min_weight=0):
    """
    Prune the net-net overlap edge list (net->net) to reduce graph density.

    Args:
      n2n_src, n2n_dst, n2n_weight: parallel lists for overlap edges
      topk: keep only top-k highest-weight neighbors for each source net (0 disables)
      min_weight: drop edges with weight < min_weight (0 disables)
    """
    if not n2n_weight:
        return n2n_src, n2n_dst, n2n_weight

    if topk <= 0 and min_weight <= 0:
        return n2n_src, n2n_dst, n2n_weight

    src = np.asarray(n2n_src, dtype=np.int64)
    dst = np.asarray(n2n_dst, dtype=np.int64)
    w = np.asarray(n2n_weight, dtype=np.int32)

    if min_weight > 0:
        mask = w >= int(min_weight)
        src = src[mask]
        dst = dst[mask]
        w = w[mask]
        if w.size == 0:
            return [], [], []

    if topk <= 0:
        return src.tolist(), dst.tolist(), w.tolist()

    # Sort by src so we can slice contiguous groups.
    order = np.argsort(src, kind="stable")
    src_s = src[order]
    dst_s = dst[order]
    w_s = w[order]

    # Iterate over groups of equal src.
    unique_src, starts = np.unique(src_s, return_index=True)
    ends = np.append(starts[1:], src_s.shape[0])

    keep_indices = []
    for st, en in zip(starts, ends):
        size = en - st
        if size <= topk:
            keep_indices.append(np.arange(st, en, dtype=np.int64))
            continue
        # Choose top-k by weight within this slice.
        slice_w = w_s[st:en]
        idx_part = np.argpartition(slice_w, -topk)[-topk:]
        # Deterministic ordering inside kept edges: descending weight, then dst.
        # Sort by (-w, dst)
        cand_w = slice_w[idx_part]
        cand_dst = dst_s[st:en][idx_part]
        inner_order = np.lexsort((cand_dst, -cand_w))
        chosen = idx_part[inner_order]
        keep_indices.append((st + chosen).astype(np.int64))

    keep_indices = np.concatenate(keep_indices) if keep_indices else np.array([], dtype=np.int64)
    src_p = src_s[keep_indices]
    dst_p = dst_s[keep_indices]
    w_p = w_s[keep_indices]
    return src_p.tolist(), dst_p.tolist(), w_p.tolist()

def infer_ub_from_path(graph_path):
    """
    从路径中解析 _ubXX，例如 ibm01_ub20_run01 -> 20。
    未匹配时返回 1 作为保守默认值。
    """
    m = re.search(r"_ub(\d+)", graph_path)
    if m:
        return int(m.group(1))
    return 1


def load_quality_scalar(sol_dir, labels=None):
    """
    从 solution 目录读取 quality.txt（第一个 token 作为 float）。
    若缺失或解析失败，且给定 labels，则回退为 cutsize 估计：
    count(label == 1)。
    """
    quality_path = os.path.join(sol_dir, "quality.txt")
    if not os.path.exists(quality_path):
        if labels is None:
            return None
        return float((labels == 1).sum().item())
    try:
        with open(quality_path, "r") as f:
            raw = f.readline().strip().split()
        if not raw:
            if labels is None:
                return None
            return float((labels == 1).sum().item())
        q = float(raw[0])
        if q != q:  # NaN
            if labels is None:
                return None
            return float((labels == 1).sum().item())
        return q
    except Exception:
        if labels is None:
            return None
        return float((labels == 1).sum().item())


def load_labels_from_hedges(edges_path):
    """
    从 hedges.txt 读取每行的 label（第三列），返回 (num_nets,) 的 tensor。
    """
    labels = []
    with open(edges_path, "r") as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 3:
                labels.append(0.0)
                continue
            try:
                labels.append(float(parts[2]))
            except (ValueError, TypeError):
                labels.append(0.0)
    return th.tensor(labels, dtype=th.float32).reshape(-1, 1)


def buildGraphStructure(
    graph_path,
    use_node2vec=False,
    use_pagerank=False,
    use_node2vec_disk_cache=False,
    pin_struct_feat_mode='homo',
    prune_overlap_topk=0,
    prune_overlap_min_weight=0,
):
    """
    Parse graph structure only (design-level, shared across solutions).
    Returns DGL graph with: pin feat, net feat (net size), edges, original_net_ids.
    Does NOT include: labels, ub, quality (those are per-solution; use attachSolutionData).
    """
    print(f"Parsing graph structure: {graph_path}")

    # 1. Read pin features (nodes.txt)
    pin_feats_list = []
    nidMap = {}
    nodes_file = os.path.join(graph_path, "nodes.txt")
    if not os.path.exists(nodes_file):
        print(f"Error: {nodes_file} not found.")
        return None
    with open(nodes_file, 'r') as f:
        for idx, line in enumerate(f):
            parts = line.strip().split()
            if not parts:
                continue
            original_id = int(parts[0])
            try:
                feats = [float(x) for x in parts[1:]]
            except ValueError:
                continue
            if len(feats) == 0:
                continue
            nidMap[original_id] = idx
            pin_feats_list.append(feats)
    pin_feat_tensor = th.tensor(pin_feats_list, dtype=th.float32)

    # 2. Read net connectivity structure (hedges.txt) - pins per net only, no labels
    p2n_src = []
    p2n_dst = []
    original_net_ids = []
    pin_to_nets = defaultdict(list)
    net_to_pins = defaultdict(list)

    edges_file = os.path.join(graph_path, "hedges.txt")
    if not os.path.exists(edges_file):
        print(f"Error: {edges_file} not found.")
        return None
    with open(edges_file, 'r') as f:
        lines = f.readlines()
    for net_idx, line in enumerate(lines):
        parts = line.strip().split(';')
        if len(parts) < 3:
            continue
        orig_net_id = int(parts[0])
        original_net_ids.append(orig_net_id)
        node_list_raw = parts[1].strip().split()
        for n_str in node_list_raw:
            if not n_str:
                continue
            raw_nid = int(n_str)
            if raw_nid in nidMap:
                pin_idx = nidMap[raw_nid]
                p2n_src.append(pin_idx)
                p2n_dst.append(net_idx)
                pin_to_nets[pin_idx].append(net_idx)
                net_to_pins[net_idx].append(pin_idx)

    # 3. Compute net-net overlaps (exact, sparse B^T*B)
    num_pins = len(pin_feats_list)
    num_nets = len(original_net_ids)
    n2n_src, n2n_dst, n2n_weight = _compute_net_overlaps_sparse(
        num_pins=num_pins,
        num_nets=num_nets,
        p2n_src=p2n_src,
        p2n_dst=p2n_dst,
    )

    # 3.5 Optional pruning of the net-net overlap graph.
    n2n_src, n2n_dst, n2n_weight = _prune_net_overlap_edges(
        n2n_src,
        n2n_dst,
        n2n_weight,
        topk=prune_overlap_topk,
        min_weight=prune_overlap_min_weight,
    )

   
    # 4. Pin structural features (clustering/2nd-order degree)
    if pin_struct_feat_mode == 'homo':
        pin_struct = _compute_pin_structural_feats(num_pins, p2n_src, p2n_dst)
    elif pin_struct_feat_mode == 'hetero':
        pin_struct = _compute_pin_structural_feats_hetero(
            num_pins=num_pins,
            num_nets=num_nets,
            pin_to_nets=pin_to_nets,
            net_to_pins=net_to_pins,
        )
    else:
        raise ValueError(f"Unknown pin_struct_feat_mode: {pin_struct_feat_mode}")
    pin_feat_tensor = th.cat([pin_feat_tensor, pin_struct], dim=1)
    if use_pagerank:
        if pin_struct_feat_mode == 'homo':
            pin_pr = _compute_pin_pagerank(num_pins, p2n_src, p2n_dst)
        else:
            # Hetero PageRank when using heterogeneous structural features.
            pin_pr = _compute_pin_pagerank_hetero(
                num_pins=num_pins,
                num_nets=num_nets,
                pin_to_nets=pin_to_nets,
                net_to_pins=net_to_pins,
            )
        pin_feat_tensor = th.cat([pin_feat_tensor, pin_pr], dim=1)
    if use_node2vec:
        pin_node2vec = _compute_pin_node2vec(
            num_pins, p2n_src, p2n_dst,
            graph_path=graph_path,
            use_disk_cache=use_node2vec_disk_cache,
        )
        if pin_node2vec is not None:
            pin_feat_tensor = th.cat([pin_feat_tensor, pin_node2vec], dim=1)

    # 5. Build DGL heterograph (structure only)
    t_p2n_src = th.tensor(p2n_src, dtype=th.int64)
    t_p2n_dst = th.tensor(p2n_dst, dtype=th.int64)
    graph_data = {
        ('pin', 'connected', 'net'): (t_p2n_src, t_p2n_dst),
        ('net', 'connected', 'pin'): (t_p2n_dst, t_p2n_src),
        ('net', 'overlap', 'net'): (th.tensor(n2n_src, dtype=th.int64),
                                    th.tensor(n2n_dst, dtype=th.int64))
    }
    g = dgl.heterograph(graph_data)

    # 6. Structural features only (no labels, ub, quality)
    g.nodes['pin'].data['feat'] = pin_feat_tensor
    net_sizes = np.zeros(num_nets, dtype=np.float32)
    for net_idx in p2n_dst:
        net_sizes[net_idx] += 1
    # Compress heavy-tailed net sizes so very large hyperedges do not dominate.
    net_size_feat = np.log1p(net_sizes)
    g.nodes['net'].data['feat'] = th.tensor(net_size_feat, dtype=th.float32).reshape(-1, 1)
    g.nodes['net'].data['id'] = th.tensor(original_net_ids, dtype=th.int32).reshape(-1, 1)
    if n2n_weight:
        g.edges['overlap'].data['weight'] = th.tensor(n2n_weight, dtype=th.float32).reshape(-1, 1)

    print(f'\t--- Structure: {g.num_nodes("pin")} Pin1s, {g.num_nodes("net")} Nets ---')
    return g

