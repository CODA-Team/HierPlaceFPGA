#!/usr/bin/env python3
"""
Run HyperCutNet inference on a single graph and write cut probabilities.

Usage:
  python inference.py --graph_dir <dir_with_nodes_hedges> --checkpoint <model.pth> -o cut_prob.txt

Input: graph_dir must contain nodes.txt and hedges.txt (HyperCutNet format).
Output: One float per line, in hyperedge order; line i = P(net i is cut).

Notes:
  - Feature normalization must match train.py: both pin and net features are z-scored
    (mean=0, std=1) before the model. Omitting net normalization causes predictions to saturate at 1.
  - hidden_dim and layers must match the trained model (default: 128, 3).
  - Used by run_guided_partition.sh for TritonPart cut-probability-guided coarsening.
"""
import os
import sys
import argparse
import hashlib
import json
import time
from functools import lru_cache
import torch
import dgl

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import buildGraphStructure, infer_ub_from_path
from graphdataset import normalize_graph_inplace, get_overlap_weights
from model import NetPredictor


def _load_training_args_from_checkpoint(checkpoint_path: str) -> argparse.Namespace | None:
    """
    Training saves a pickled argparse Namespace at:
      <checkpoint_dir>/args.pkl
    """
    if not checkpoint_path:
        return None

    ckpt_dir = checkpoint_path
    if os.path.isfile(checkpoint_path):
        ckpt_dir = os.path.dirname(checkpoint_path)

    args_path = os.path.join(ckpt_dir, "args.pkl")
    if not os.path.exists(args_path):
        return None

    try:
        return torch.load(args_path, map_location="cpu", weights_only=False)
    except Exception:
        return None


def _structure_cache_path(
    graph_dir: str,
    use_node2vec: bool,
    use_pagerank: bool,
    pin_struct_feat_mode: str,
    prune_overlap_topk: int,
    prune_overlap_min_weight: int,
) -> str:
    """
    Disk cache for the graph structure (nodes/edges + structural node features).
    Keyed by:
      - absolute graph_dir
      - content timestamps/sizes of nodes.txt and hedges.txt (to avoid stale cache)
    """
    abs_graph_dir = os.path.abspath(graph_dir)
    nodes_path = os.path.join(graph_dir, "nodes.txt")
    hedges_path = os.path.join(graph_dir, "hedges.txt")

    def _stat_sig(p: str) -> str:
        try:
            st = os.stat(p)
            return f"{st.st_mtime_ns}:{st.st_size}"
        except FileNotFoundError:
            return "missing"

    key_base = (
        f"{abs_graph_dir}|"
        f"node2vec={int(use_node2vec)}|"
        f"pagerank={int(use_pagerank)}|"
        f"pin_struct_feat_mode={pin_struct_feat_mode}|"
        f"prune_overlap_topk={int(prune_overlap_topk)}|"
        f"prune_overlap_min_weight={int(prune_overlap_min_weight)}|"
        f"nodes_sig={_stat_sig(nodes_path)}|"
        f"hedges_sig={_stat_sig(hedges_path)}"
    )
    key = hashlib.sha1(key_base.encode("utf-8")).hexdigest()[:16]
    cache_dir = os.path.join(graph_dir, ".hypercutnet_struct_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"structure_{key}.bin")


@lru_cache(maxsize=8)
def _load_or_build_structure(
    graph_dir: str,
    use_node2vec: bool,
    use_pagerank: bool,
    use_node2vec_disk_cache: bool,
    pin_struct_feat_mode: str,
    prune_overlap_topk: int,
    prune_overlap_min_weight: int,
) -> dgl.DGLHeteroGraph:
    cache_path = _structure_cache_path(
        graph_dir,
        use_node2vec,
        use_pagerank,
        pin_struct_feat_mode,
        prune_overlap_topk,
        prune_overlap_min_weight,
    )
    if os.path.exists(cache_path):
        graphs, _ = dgl.load_graphs(cache_path)
        if len(graphs) != 1:
            raise RuntimeError(f"Unexpected structure cache content: {cache_path}")
        return graphs[0]

    structure_g = buildGraphStructure(
        graph_dir,
        use_node2vec=use_node2vec,
        use_pagerank=use_pagerank,
        use_node2vec_disk_cache=use_node2vec_disk_cache,
        pin_struct_feat_mode=pin_struct_feat_mode,
        prune_overlap_topk=prune_overlap_topk,
        prune_overlap_min_weight=prune_overlap_min_weight,
    )
    if structure_g is None:
        raise RuntimeError(f"Failed to build graph structure from {graph_dir}")
    dgl.save_graphs(cache_path, [structure_g])
    return structure_g


def _num_nets_from_hedges(graph_dir: str) -> int:
    hedges_path = os.path.join(graph_dir, "hedges.txt")
    if not os.path.exists(hedges_path):
        raise FileNotFoundError(f"hedges.txt not found in {graph_dir}")
    with open(hedges_path, "r") as f:
        return sum(1 for ln in f if ln.strip())


def _parse_bool01(v: str) -> bool:
    v = str(v).strip().lower()
    if v in ("1", "true", "t", "yes", "y"):
        return True
    if v in ("0", "false", "f", "no", "n"):
        return False
    raise ValueError(f"Expected 0/1, got: {v}")


def run_inference(graph_dir: str, checkpoint_path: str | None, output_path: str,
                  ub_factor: int | None = None, ub_max: int = 20,
                  use_node2vec_disk_cache: bool | None = None) -> None:
    t_total0 = time.perf_counter()
    timing = {
        "feature_structure_sec": 0.0,
        "feature_ub_sec": 0.0,
        "feature_normalize_overlap_sec": 0.0,
        "model_load_sec": 0.0,
        "model_forward_sec": 0.0,
        "write_sec": 0.0,
    }
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # A checkpoint is required because the model architecture and feature
    # settings are recovered from its adjacent args.pkl file.
    if not (checkpoint_path and os.path.exists(checkpoint_path)):
        raise RuntimeError(f"checkpoint not found: {checkpoint_path}")
    else:
        # Load architecture + feature flags strictly from the checkpoint.
        ckpt_args = _load_training_args_from_checkpoint(checkpoint_path)
        if ckpt_args is None:
            raise RuntimeError(f"args.pkl missing next to checkpoint: {checkpoint_path}")

        hidden_dim = getattr(ckpt_args, "hidden_dim", None)
        layers = getattr(ckpt_args, "layers", None)
        use_node2vec = bool(getattr(ckpt_args, "use_node2vec", False))
        use_pagerank = bool(getattr(ckpt_args, "use_pagerank", False))
        use_ubfactor = bool(getattr(ckpt_args, "use_ubfactor", False))
        pin_struct_feat_mode = str(getattr(ckpt_args, "pin_struct_feat_mode", "homo"))
        prune_overlap_topk = int(getattr(ckpt_args, "prune_overlap_topk", 0))
        prune_overlap_min_weight = int(getattr(ckpt_args, "prune_overlap_min_weight", 0))
        
        ub_isolate = bool(getattr(ckpt_args, "ub_isolate", False)) and use_ubfactor
        pin2net_type = str(getattr(ckpt_args, "pin2net_type", "gat"))
        pin2net_gat_heads = int(getattr(ckpt_args, "pin2net_gat_heads", 4))
        pin2net_gat_feat_drop = float(getattr(ckpt_args, "pin2net_gat_feat_drop", 0.0))
        pin2net_gat_attn_drop = float(getattr(ckpt_args, "pin2net_gat_attn_drop", 0.0))
        pin2net_gat_chunk_nets = int(getattr(ckpt_args, "pin2net_gat_chunk_nets", 0))
        net2net_type = str(getattr(ckpt_args, "net2net_type", "graphconv"))
        net2net_gat_heads = int(getattr(ckpt_args, "net2net_gat_heads", 4))
        net2net_gat_feat_drop = float(getattr(ckpt_args, "net2net_gat_feat_drop", 0.0))
        net2net_gat_attn_drop = float(getattr(ckpt_args, "net2net_gat_attn_drop", 0.0))
        net2pin_type = str(getattr(ckpt_args, "net2pin_type", "graphconv"))
        net2pin_gat_heads = int(getattr(ckpt_args, "net2pin_gat_heads", 4))
        net2pin_gat_feat_drop = float(getattr(ckpt_args, "net2pin_gat_feat_drop", 0.0))
        net2pin_gat_attn_drop = float(getattr(ckpt_args, "net2pin_gat_attn_drop", 0.0))

        if hidden_dim is None or layers is None:
            raise RuntimeError("args.pkl missing hidden_dim/layers in checkpoint")

        # 1) Load/build structure once (disk cached).
        t0 = time.perf_counter()
        structure_g = _load_or_build_structure(
            graph_dir,
            use_node2vec,
            use_pagerank,
            use_node2vec_disk_cache,
            pin_struct_feat_mode,
            prune_overlap_topk,
            prune_overlap_min_weight,
        )
        timing["feature_structure_sec"] = time.perf_counter() - t0
        g = structure_g.clone()

        # 2) Attach UB-conditioned feature if the model was trained with it.
        t0 = time.perf_counter()
        if use_ubfactor:
            num_nets = g.num_nodes("net")
            ub_val = ub_factor if ub_factor is not None else infer_ub_from_path(graph_dir)
            ub_max_safe = float(max(int(ub_max), 1))
            ub_norm = float(ub_val) / ub_max_safe
            ub_col = torch.full((num_nets, 1), ub_norm, dtype=torch.float32)
            if ub_isolate:
                g.nodes["net"].data["ub"] = ub_col
            else:
                g.nodes["net"].data["feat"] = torch.cat(
                    [g.nodes["net"].data["feat"], ub_col], dim=1
                )
        timing["feature_ub_sec"] = time.perf_counter() - t0

        # 3) Build model and run inference.
        num_nets = g.num_nodes("net")
        pin_in_dim = g.nodes["pin"].data["feat"].shape[1]
        net_in_dim = g.nodes["net"].data["feat"].shape[1]

        t0 = time.perf_counter()
        model = NetPredictor(
            pin_in_dim=pin_in_dim,
            net_in_dim=net_in_dim,
            hidden_dim=int(hidden_dim),
            out_dim=1,
            n_layers=int(layers),
            ub_isolate=ub_isolate,
            pin2net_type=pin2net_type,
            pin2net_gat_heads=pin2net_gat_heads,
            pin2net_gat_feat_drop=pin2net_gat_feat_drop,
            pin2net_gat_attn_drop=pin2net_gat_attn_drop,
            pin2net_gat_chunk_nets=pin2net_gat_chunk_nets,
            net2net_type=net2net_type,
            net2net_gat_heads=net2net_gat_heads,
            net2net_gat_feat_drop=net2net_gat_feat_drop,
            net2net_gat_attn_drop=net2net_gat_attn_drop,
            net2pin_type=net2pin_type,
            net2pin_gat_heads=net2pin_gat_heads,
            net2pin_gat_feat_drop=net2pin_gat_feat_drop,
            net2pin_gat_attn_drop=net2pin_gat_attn_drop,
        ).to(device)
        model.load_state_dict(torch.load(checkpoint_path, map_location=device))
        model.eval()
        timing["model_load_sec"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        g = g.to(device)
        normalize_graph_inplace(g)
        pin_feat = g.nodes["pin"].data["feat"]
        overlap_weights = get_overlap_weights(
            g,
            normalize_overlap_weights=bool(getattr(ckpt_args, 'normalize_overlap_weights', False)),
        )
        timing["feature_normalize_overlap_sec"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        with torch.no_grad():
            logits, _ = model(g, pin_feat, overlap_weights)
        probs = torch.sigmoid(logits).squeeze(-1).cpu().numpy()
        timing["model_forward_sec"] = time.perf_counter() - t0

    # 5. Write one float per line, in hyperedge order (TritonPart expects this)
    t0 = time.perf_counter()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for p in probs:
            f.write(f"{float(p)}\n")
    timing["write_sec"] = time.perf_counter() - t0
    timing["feature_sec"] = (
        timing["feature_structure_sec"]
        + timing["feature_ub_sec"]
        + timing["feature_normalize_overlap_sec"]
    )
    timing["inference_sec"] = timing["model_load_sec"] + timing["model_forward_sec"]
    timing["total_sec"] = time.perf_counter() - t_total0

    print(f"Wrote {num_nets} cut probabilities to {output_path}")
    print("TIMING_JSON " + json.dumps(timing, sort_keys=True))


def main():
    ap = argparse.ArgumentParser(description="HyperCutNet inference: predict cut probabilities per net")
    ap.add_argument("--graph_dir", type=str, required=True, help="Dir with nodes.txt and hedges.txt")
    ap.add_argument("--checkpoint", type=str, required=True, help="Model checkpoint .pth path")
    ap.add_argument("-o", "--output", type=str, required=True, help="Output cut probability file")
    ap.add_argument("--ub_factor", type=int, default=None,
                    help="Optional explicit UB value for one graph; default parses from graph_dir name")
    ap.add_argument("--ub_max", type=int, default=20,
                    help="Normalize UB by ub_max (only used if checkpoint enables use_ubfactor)")
    ap.add_argument(
        "--use_node2vec_disk_cache",action="store_true",
        help="0/1: override whether to load/save node2vec embeddings to disk during inference. "
             "If omitted, uses checkpoint args.pkl.",
    )
    args = ap.parse_args()

    run_inference(
        graph_dir=args.graph_dir,
        checkpoint_path=args.checkpoint,
        output_path=args.output,
        ub_factor=args.ub_factor,
        ub_max=args.ub_max,
        use_node2vec_disk_cache= args.use_node2vec_disk_cache
    )


if __name__ == "__main__":
    main()
