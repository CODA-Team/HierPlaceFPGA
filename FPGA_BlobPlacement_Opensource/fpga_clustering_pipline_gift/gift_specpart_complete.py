"""
FPGA Clustering Pipeline: Louvain -> GIFT -> SpecPart (Complete Integration)
=============================================================================

完整流程:
1. 解析FPGA文件 (.nodes, .nets, .pl, etc.)
2. Louvain聚类得到大cluster
3. GIFT对大cluster进行布局得到x/y坐标
4. SpecPart使用x/y坐标作为特征向量进行分区
   - 构建多棵树 (GenTrees)
   - 树分区获取候选方案 (Tree Partitioning)
   - Cut-Overlay聚类
   - 最终分区

基于:
- GIFT: Graph-based FPGA Layout (混合频率滤波器)
- SpecPart: A Supervised Spectral Framework for Hypergraph Partitioning
"""

import os
import re
import time
import numpy as np
from scipy.sparse import csc_matrix, csr_matrix, lil_matrix, identity, coo_matrix, diags
from scipy.sparse import csgraph, linalg as sp_linalg
from scipy.sparse.csgraph import minimum_spanning_tree, dijkstra
from collections import defaultdict
import json
import subprocess
import tempfile
import shutil
import uuid
try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError:
    gp = None
    GRB = None

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))


def _first_existing_path(*paths):
    for path in paths:
        if path and os.path.exists(path):
            return path
    return paths[0] if paths else ""


DEFAULT_SPECPART_ROOT = os.environ.get("SPECPART_ROOT") or os.path.join(
    PROJECT_ROOT, "external", "HypergraphPartitioning-main"
)
DEFAULT_SPECPART_JL = os.path.join(
    DEFAULT_SPECPART_ROOT, "SpecPart", "SpectralRefinement.jl"
)
DEFAULT_RECURSIVE_BISECTION_JL = os.path.join(
    DEFAULT_SPECPART_ROOT, "SpecPart", "RecursiveBisection.jl"
)
DEFAULT_K_SPECPART_JL = os.path.join(
    DEFAULT_SPECPART_ROOT, "K_SpecPart", "K_SpecPartWrapper.jl"
)
DEFAULT_HMETIS_EXEC = os.environ.get("HMETIS_EXEC") or os.path.join(
    PROJECT_ROOT, "hmetis_api", "hmetis_api", "src", "hmetis"
)

# =============================================================================
# Part 1: GIFT算法实现
# =============================================================================

class GiFt:
    """GIFT滤波器"""
    
    def __init__(self, adj_mat):
        self.adj_mat = adj_mat
        self.norm_adj = None
        self.d_mat = None
        
    def train(self, sigma):
        """训练滤波器: norm_adj = D^{-0.5} (A + σI) D^{-0.5}"""
        adj_mat = csc_matrix(self.adj_mat)
        dim = adj_mat.shape[0]
        
        adj_mat = adj_mat + sigma * identity(dim)
        rowsum = np.array(adj_mat.sum(axis=1)).flatten()
        d_inv = np.power(rowsum, -0.5)
        d_inv[np.isinf(d_inv)] = 0.
        d_mat = diags(d_inv)
        
        norm_adj = d_mat.dot(adj_mat).dot(d_mat)
        self.norm_adj = norm_adj
        self.d_mat = d_mat
        
    def new_filter_train(self):
        """替代滤波器: norm_adj = (λ_max * I - L) / λ_max"""
        adj_mat = csc_matrix(self.adj_mat)
        dim = adj_mat.shape[0]
        
        d_mat = diags(np.array(adj_mat.sum(axis=1)).flatten())
        L = d_mat - adj_mat
        L = csc_matrix(L)
        
        diag_L = L.diagonal()
        row_sum = np.abs(L).sum(axis=1).A1
        R_Gershgorin = row_sum - np.abs(diag_L)
        lambda_max = np.max(diag_L + R_Gershgorin)
        
        norm_adj = (lambda_max * identity(dim) - L) / lambda_max
        self.norm_adj = norm_adj
        
    def get_cell_position(self, k, cell_pos):
        """应用k次滤波器迭代获取新位置"""
        norm_adj = self.norm_adj
        if isinstance(cell_pos, list):
            cell_pos = np.array(cell_pos)
        for _ in range(k):
            cell_pos = norm_adj @ cell_pos
        return cell_pos


class GIFTInterface:
    """GIFT布局接口"""
    
    def __init__(self, adj_matrix, fixed_positions=None, movable_num=None):
        self.adj_matrix = adj_matrix
        self.n = adj_matrix.shape[0]
        
        if fixed_positions is not None and len(fixed_positions) > 0:
            self.fixed_positions = np.array(fixed_positions)
            self.movable_num = movable_num if movable_num else self.n - len(fixed_positions)
        else:
            self.fixed_positions = np.array([]).reshape(0, 2)
            self.movable_num = self.n
            
    def run_gift_layout(self, placement_region=None, scale=0.5, 
                        use_mixed_filter=True, seed=42):
        """运行GIFT布局"""
        print(f"    Running GIFT layout on {self.n} nodes...")
        
        if placement_region is None:
            if len(self.fixed_positions) > 0:
                x_min, y_min = self.fixed_positions.min(axis=0)
                x_max, y_max = self.fixed_positions.max(axis=0)
            else:
                x_min, y_min, x_max, y_max = 0, 0, 100, 100
        else:
            x_min, y_min, x_max, y_max = placement_region
            
        # 生成初始位置
        np.random.seed(seed)
        movable_init = np.random.rand(self.movable_num, 2)
        xcenter = (x_max + x_min) / 2
        ycenter = (y_max + y_min) / 2
        movable_init[:, 0] = ((movable_init[:, 0] - 0.5) * (x_max - x_min) * scale) + xcenter
        movable_init[:, 1] = ((movable_init[:, 1] - 0.5) * (y_max - y_min) * scale) + ycenter
        
        if len(self.fixed_positions) > 0:
            init_location = np.vstack([movable_init, self.fixed_positions])
        else:
            init_location = movable_init
            
        init_location_shifted = init_location.copy()
        init_location_shifted[:, 0] -= x_min
        init_location_shifted[:, 1] -= y_min
        
        start_time = time.time()
        
        if use_mixed_filter:
            positions = self._run_mixed_filter(init_location_shifted)
        else:
            positions = self._run_new_filter(init_location_shifted)
            
        end_time = time.time()
        print(f"    GIFT completed in {end_time - start_time:.3f}s")
        
        positions[:, 0] += x_min
        positions[:, 1] += y_min
        
        return positions
    
    def _run_mixed_filter(self, init_location):
        """混合频率滤波器"""
        gift = GiFt(self.adj_matrix)
        
        gift.train(sigma=4)
        location_low = gift.get_cell_position(k=4, cell_pos=init_location.copy())
        
        gift.train(sigma=4)
        location_mid = gift.get_cell_position(k=2, cell_pos=init_location.copy())
        
        gift.train(sigma=2)
        location_high = gift.get_cell_position(k=2, cell_pos=init_location.copy())
        
        positions = 0.2 * location_low + 0.7 * location_mid + 0.1 * location_high
        return positions
    
    def _run_new_filter(self, init_location):
        """新滤波器"""
        gift = GiFt(self.adj_matrix)
        gift.new_filter_train()
        positions = gift.get_cell_position(k=4, cell_pos=init_location.copy())
        return positions
    
    def get_xy_features(self, positions):
        """提取x/y坐标作为特征向量"""
        return positions[:, 0].copy(), positions[:, 1].copy()


# =============================================================================
# Part 2: SpecPart核心实现
# =============================================================================

class TreeGenerator:
    """树生成器 - 从特征向量生成多种类型的树"""
    
    def __init__(self, adj_matrix, eigenvectors):
        self.adj_matrix = csr_matrix(adj_matrix)
        self.eigenvectors = eigenvectors
        self.n = adj_matrix.shape[0]
        
    def modify_expander_weights(self, nev=2, use_inverse=False):
        """根据特征向量距离修改边权重"""
        rows, cols = self.adj_matrix.nonzero()
        new_weights = np.zeros(len(rows))
        
        for idx, (i, j) in enumerate(zip(rows, cols)):
            distance = 0.0
            for d in range(min(nev, self.eigenvectors.shape[1])):
                diff = abs(self.eigenvectors[i, d] - self.eigenvectors[j, d])
                if use_inverse:
                    distance += 1e9 if diff == 0.0 else 1.0 / diff
                else:
                    distance += diff
            new_weights[idx] = distance + 1e-10  # 避免零权重
            
        return csr_matrix((new_weights, (rows, cols)), shape=self.adj_matrix.shape)
    
    def gen_prim_mst(self):
        """Prim MST"""
        modified = self.modify_expander_weights(nev=self.eigenvectors.shape[1])
        mst = minimum_spanning_tree(modified)
        return csr_matrix(mst) + csr_matrix(mst).T
    
    def gen_path_tree(self):
        """路径树"""
        eig_0 = self.eigenvectors[:, 0]
        nodes = np.argsort(eig_0)
        
        i = nodes[:-1]
        j = nodes[1:]
        w = np.abs(eig_0[j] - eig_0[i])
        w[w == 0.0] = 1e6
        
        tree = csr_matrix((w, (i, j)), shape=(self.n, self.n))
        return tree + tree.T
    
    def generate_shortest_path_trees(self, roots):
        """生成最短路径树"""
        trees = []
        modified = self.modify_expander_weights(nev=self.eigenvectors.shape[1])
        
        for root in roots:
            dist_matrix, predecessors = dijkstra(
                csgraph=modified, directed=False, indices=root, return_predecessors=True
            )
            
            rows, cols, weights = [], [], []
            for k in range(self.n):
                if k != root and predecessors[k] >= 0:
                    rows.append(k)
                    cols.append(predecessors[k])
                    weights.append(modified[k, predecessors[k]])
            
            tree = csr_matrix((weights, (rows, cols)), shape=(self.n, self.n))
            trees.append(tree + tree.T)
            
        return trees
    
    def generate_all_trees(self, num_spt=3):
        """生成所有类型的树"""
        trees = []
        
        # Prim MST
        try:
            trees.append(self.gen_prim_mst())
        except Exception as e:
            print(f"    Warning: Prim MST failed: {e}")
        
        # Path Tree
        try:
            trees.append(self.gen_path_tree())
        except Exception as e:
            print(f"    Warning: Path tree failed: {e}")
        
        # Shortest Path Trees
        if self.n > 0:
            eig_0 = self.eigenvectors[:, 0]
            sorted_idx = np.argsort(eig_0)
            step = max(1, len(sorted_idx) // (num_spt + 1))
            roots = [sorted_idx[i * step] for i in range(1, num_spt + 1)][:num_spt]
            
            try:
                spt = self.generate_shortest_path_trees(roots)
                trees.extend(spt)
            except Exception as e:
                print(f"    Warning: SPT failed: {e}")
        
        return trees


class TreePartitioner:
    """树分区器"""
    
    def __init__(self, tree, vertex_weights=None, ub_factor=10):
        self.tree = csr_matrix(tree)
        self.n = tree.shape[0]
        self.vertex_weights = vertex_weights if vertex_weights is not None else np.ones(self.n)
        self.ub_factor = ub_factor
        
        total_weight = np.sum(self.vertex_weights)
        self.max_capacity = int(np.ceil(total_weight * (50 + ub_factor) / 100))
        self.min_capacity = total_weight - self.max_capacity
        
    def sweep_partition(self, order):
        """沿顺序扫描树寻找最佳切割"""
        n = len(order)
        cumsum = np.cumsum(self.vertex_weights[order])
        total = cumsum[-1]
        
        best_cut = float('inf')
        best_split = n // 2
        
        for i in range(n - 1):
            part0_weight = cumsum[i]
            part1_weight = total - part0_weight
            
            if (self.min_capacity <= part0_weight <= self.max_capacity and
                self.min_capacity <= part1_weight <= self.max_capacity):
                cut = self._compute_cut(order, i)
                if cut < best_cut:
                    best_cut = cut
                    best_split = i
        
        partition = np.zeros(self.n, dtype=int)
        partition[order[best_split + 1:]] = 1
        
        return partition, best_cut
    
    def _compute_cut(self, order, split_idx):
        """计算切割数（树边权 cut），返回 float 标量"""
        part0 = set(order[:split_idx + 1])
        part1 = set(order[split_idx + 1:])

        cut = 0.0
        rows, cols = self.tree.nonzero()
        for i, j in zip(rows, cols):
            if i < j:
                if (i in part0 and j in part1) or (i in part1 and j in part0):
                    cut += float(self.tree[i, j])
        return float(cut)
    
    def partition_by_eigenvector(self, eigenvector):
        """使用特征向量顺序分区"""
        order = np.argsort(eigenvector)
        return self.sweep_partition(order)


class UnionFind:
    """并查集 (Union-Find) - 用于 Cut-Overlay 后的连通分量聚类"""

    def __init__(self, n: int):
        self.parent = np.arange(n, dtype=int)
        self.size = np.ones(n, dtype=int)

    def find(self, x: int) -> int:
        # 路径压缩
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        # union by size
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


class CutOverlayClustering:
    """Cut-Overlay 聚类（与 SpecPart/Clustering.jl 对齐）

    关键点：
    - 不再使用“节点 partition pattern 相同就归一类”的 overlay。
    - 按照 SpecPart 的实现：
      1) 对候选分区集合 bins(=partition_matrix) 计算 **union of cut hyperedges**
      2) 从超图中删除这些“被任何候选分区切到的超边”
      3) 在剩余超边上做连通分量 (connected components)，得到 cluster / super-nodes
    """

    def __init__(self, num_vertices, hyperedges, hyperedge_weights=None, vertex_weights=None):
        self.n = int(num_vertices)
        self.hyperedges = list(hyperedges)
        self.hyperedge_weights = (
            list(hyperedge_weights) if hyperedge_weights is not None else [1.0] * len(self.hyperedges)
        )
        self.vertex_weights = (
            np.asarray(vertex_weights, dtype=float) if vertex_weights is not None else np.ones(self.n, dtype=float)
        )

    def select_best_partitions(self, partition_matrix, cuts, top_k=5, dedup=True):
        """选择最佳分区：按 cuts 排序，支持去重。

        Returns:
            selected_matrix: (k, n)
            selected_cuts:   (k,)
        """
        partition_matrix = np.asarray(partition_matrix)
        cuts = np.asarray(cuts, dtype=float)
        m = partition_matrix.shape[0]
        if m == 0:
            return partition_matrix, cuts

        order = np.argsort(cuts)

        selected_parts = []
        selected_cuts = []
        seen = set()

        for idx in order:
            p = np.asarray(partition_matrix[idx], dtype=np.int8)
            key = p.tobytes()
            if dedup and key in seen:
                continue
            seen.add(key)
            selected_parts.append(p)
            selected_cuts.append(float(cuts[idx]))
            if len(selected_parts) >= int(top_k):
                break

        return np.asarray(selected_parts, dtype=np.int8), np.asarray(selected_cuts, dtype=float)

    def _is_cut_hyperedge(self, hedge, part_vec) -> bool:
        """判断超边是否被二分 partition 切到"""
        if len(hedge) <= 1:
            return False
        base = part_vec[hedge[0]]
        for v in hedge[1:]:
            if part_vec[v] != base:
                return True
        return False

    def cut_overlay_clustering(self, partition_matrix):
        """SpecPart Cut-Overlay 聚类：union-cut 去边 + 连通分量"""
        bins = np.asarray(partition_matrix)
        if bins.ndim != 2:
            raise ValueError('partition_matrix must be 2D: (m, n)')
        m, n = bins.shape
        if n != self.n:
            raise ValueError(f'partition_matrix n={n} != num_vertices={self.n}')

        e = len(self.hyperedges)
        if m == 0 or e == 0:
            # 没有 bins 或没有超边：每个点单独成簇
            cluster_map = np.arange(self.n, dtype=int)
            clusters = [[i] for i in range(self.n)]
            cluster_sizes = np.ones(self.n, dtype=int)
            cut_union = np.zeros(e, dtype=bool)
            return clusters, cluster_map, cluster_sizes, cut_union

        # 1) union of cut hyperedges
        cut_union = np.zeros(e, dtype=bool)
        for i in range(m):
            part_vec = bins[i]
            for eid, hedge in enumerate(self.hyperedges):
                if cut_union[eid]:
                    continue
                if self._is_cut_hyperedge(hedge, part_vec):
                    cut_union[eid] = True

        # 2) 连通分量：只用“未被任何候选分区切到”的超边连接
        uf = UnionFind(self.n)
        for eid, hedge in enumerate(self.hyperedges):
            if cut_union[eid]:
                continue
            if len(hedge) <= 1:
                continue
            base = hedge[0]
            # Julia 版是按 hedge 内顺序链式 union，这里用 base 与其余 union，连通性等价
            for v in hedge[1:]:
                uf.union(base, v)

        # 3) 生成 cluster_map (vertex -> cluster_id) 与 clusters
        root_to_cid = {}
        cluster_map = np.zeros(self.n, dtype=int)
        clusters = []
        for v in range(self.n):
            r = uf.find(v)
            cid = root_to_cid.get(r)
            if cid is None:
                cid = len(root_to_cid)
                root_to_cid[r] = cid
                clusters.append([])
            cluster_map[v] = cid
            clusters[cid].append(v)

        cluster_sizes = np.asarray([len(c) for c in clusters], dtype=int)
        return clusters, cluster_map, cluster_sizes, cut_union

    def generate_clustered_hypergraph(self, clusters, cluster_map):
        """根据 clusters/cluster_map 生成收缩后的超图 (clustered hypergraph)"""
        clusters = list(clusters)
        cluster_map = np.asarray(cluster_map, dtype=int)
        n_cc = len(clusters)
        if n_cc == 0:
            return [], [], np.asarray([], dtype=float)

        # super-node 权重 = 所含原始点权重之和
        cluster_weights = np.zeros(n_cc, dtype=float)
        for cid, verts in enumerate(clusters):
            cluster_weights[cid] = float(self.vertex_weights[np.asarray(verts, dtype=int)].sum())

        # 收缩超边并合并重复：key = (sorted unique cluster ids)
        hedge_weight_map = defaultdict(float)
        for he_idx, hedge in enumerate(self.hyperedges):
            cset = sorted({int(cluster_map[v]) for v in hedge})
            if len(cset) < 2:
                continue
            key = tuple(cset)
            hedge_weight_map[key] += float(self.hyperedge_weights[he_idx])

        new_hyperedges = list(hedge_weight_map.keys())
        new_weights = [hedge_weight_map[k] for k in new_hyperedges]
        return new_hyperedges, new_weights, cluster_weights


class GurobiILPPartitioner:
    def __init__(self, num_vertices, hyperedges, ub_factor=10, gamma=300):
        self.n = num_vertices
        self.hyperedges = hyperedges
        self.ub_factor = ub_factor  # The load balance factor, e.g., 10 for 45-55 split
        self.gamma = gamma          # Threshold for using Gurobi ILP

    def run_ilp_partitioning(self):
        """运行 Gurobi ILP 求解超图的分区"""
        t0 = time.time()
        print(f"    [ILP] Starting Gurobi ILP: vertices={self.n}, hyperedges={len(self.hyperedges)}, ub={self.ub_factor}")
        if gp is None or GRB is None:
            print("    [ILP] gurobipy is not installed; skip Gurobi ILP fallback")
            return None
        try:
            # 创建一个优化模型
            model = gp.Model("Hypergraph Partitioning")
            model.setParam('OutputFlag', 0)  # suppress Gurobi output for cleaner logs

            # 创建变量: y_{i,k} -> 节点 i 是否分配到簇 k
            y = model.addVars(self.n, 2, vtype=GRB.BINARY, name="y")

            # 创建变量: x_{u,v} -> 节点 u 和 v 是否分配到不同的簇
            x = model.addVars(self.n, self.n, vtype=GRB.BINARY, name="x")

            # 目标函数: 最小化跨簇的超边数量
            model.setObjective(
                gp.quicksum(x[u, v] for edge in self.hyperedges for u in edge for v in edge),
                GRB.MINIMIZE
            )

            # 约束：每个节点只能分配到一个簇
            for i in range(self.n):
                model.addConstr(gp.quicksum(y[i, k] for k in range(2)) == 1)

            # 约束：跨簇的惩罚
            for edge in self.hyperedges:
                for u in edge:
                    for v in edge:
                        if u != v:
                            model.addConstr(x[u, v] == abs(y[u, 0] - y[v, 0]))

            # 约束：每个簇的大小平衡
            total_weight = self.n  # Assume equal weights for simplicity
            max_capacity = total_weight * (50 + self.ub_factor) / 100
            min_capacity = total_weight - max_capacity
            model.addConstrs(gp.quicksum(y[i, k] for i in range(self.n)) <= max_capacity for k in range(2))
            model.addConstrs(gp.quicksum(y[i, k] for i in range(self.n)) >= min_capacity for k in range(2))

            # 求解模型
            model.optimize()
            elapsed = time.time() - t0

            # 获取分区结果
            if model.status == GRB.OPTIMAL:
                partition = {}
                for i in range(self.n):
                    for k in range(2):
                        if y[i, k].x > 0.5:
                            partition[i] = k
                print(f"    [ILP] Gurobi optimal in {elapsed:.2f}s, objval={model.objVal:.1f}")
                return partition
            else:
                print(f"    [ILP] Gurobi no optimal solution (status={model.status}) after {elapsed:.2f}s")
                return None
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    [ILP] Gurobi ILP failed after {elapsed:.2f}s: {e}")
            return None


class HypergraphPartitioner:
    """超图二分器（用于 Step4/Step7 的 golden partition / baseline）"""

    def __init__(self, num_vertices, hyperedges, vertex_weights=None, hyperedge_weights=None, ub_factor=10, gamma=300):
        self.n = int(num_vertices)
        self.hyperedges = list(hyperedges)
        self.vertex_weights = (
            np.asarray(vertex_weights, dtype=float) if vertex_weights is not None else np.ones(self.n, dtype=float)
        )
        self.hyperedge_weights = (
            list(hyperedge_weights) if hyperedge_weights is not None else [1.0] * len(self.hyperedges)
        )
        self.ub_factor = int(ub_factor)
        self.gamma = gamma

        total_weight = float(np.sum(self.vertex_weights))
        self.max_capacity = float(np.ceil(total_weight * (50 + self.ub_factor) / 100.0))
        self.min_capacity = total_weight - self.max_capacity

        # 构建 incidence: vertex -> incident hyperedges
        self._inc = [[] for _ in range(self.n)]
        for eid, hedge in enumerate(self.hyperedges):
            for v in hedge:
                self._inc[int(v)].append(eid)

    def write_hmetis_format(self, filepath):
        """写入 hMETIS 格式（不含权重版本）"""
        with open(filepath, 'w') as f:
            f.write(f"{len(self.hyperedges)} {self.n}\n")
            for hedge in self.hyperedges:
                f.write(' '.join(str(int(v) + 1) for v in hedge) + '\n')

    def run_hmetis(self, hmetis_path="hmetis", num_parts=2, nruns=10, seed=0):
        """调用 hMETIS 做二分（如果可用），返回 (partition, cut)"""
        print(f"Running hmetis with path: {hmetis_path} for {num_parts} parts, seed={seed}")
        if shutil.which(hmetis_path) is None and not os.path.exists(hmetis_path):
            print("hmetis not found or not in PATH")
            return None, float('inf')

        with tempfile.TemporaryDirectory() as tmpdir:
            hg_file = os.path.join(tmpdir, "hypergraph.hgr")
            self.write_hmetis_format(hg_file)

            cmd = [
                hmetis_path,
                hg_file,
                str(int(num_parts)),
                str(int(self.ub_factor)),
                str(int(nruns)),
                "1",
                "1",
                "0",
                "1",
                "0",
                str(int(seed)),
            ]

            try:
                subprocess.run(cmd, capture_output=True, timeout=300, check=False)
                part_file = f"{hg_file}.part.{int(num_parts)}"
                if os.path.exists(part_file):
                    partition = np.loadtxt(part_file, dtype=int)
                    if partition.ndim == 0:
                        partition = np.asarray([int(partition)], dtype=int)
                    return partition.astype(int), float(self._compute_cutsize(partition))
            except Exception:
                pass

        return None, float('inf')

    def run_gurobi_ilp(self):
        """使用 Gurobi ILP 进行分区"""
        print(f"    [HgPartitioner] Running Gurobi ILP: vertices={self.n}, hyperedges={len(self.hyperedges)}")
        t0 = time.time()
        ilp_partitioner = GurobiILPPartitioner(self.n, self.hyperedges, ub_factor=self.ub_factor, gamma=self.gamma)
        partition_dict = ilp_partitioner.run_ilp_partitioning()
        elapsed = time.time() - t0

        if partition_dict is None:
             print(f"    [HgPartitioner] ILP failed after {elapsed:.2f}s, returning None")
             return None, float('inf')

        # Convert dict to array
        partition = np.zeros(self.n, dtype=int)
        for i, k in partition_dict.items():
            partition[i] = k

        cutsize = float(self._compute_cutsize(partition))
        print(f"    [HgPartitioner] ILP succeeded in {elapsed:.2f}s, cutsize={cutsize}")
        return partition, cutsize

    def partition(self):
        """根据超边数量选择合适的分区工具"""
        num_hyperedges = len(self.hyperedges)
        if num_hyperedges <= self.gamma:
            print("Using Gurobi ILP for partitioning")
            part, cut = self.run_gurobi_ilp()
            if part is not None:
                return part, cut
        
        # 否则使用 hMETIS 或其他默认
        return self.run_hmetis(hmetis_path="/path/to/hmetis", num_parts=2, nruns=10)

    def partition_by_feature(self, feature_values):
        """
        基于特征值的线性扫描（Sweep Cut）分区
        用于 SpecPart 的 fallback 或 baseline 比较
        """
        order = np.argsort(feature_values)
        
        # 预计算每条超边的度数
        edge_degrees = np.array([len(h) for h in self.hyperedges], dtype=int)
        
        # 初始状态：所有点都在 Part 1，Part 0 为空
        # Cut 初始为 0（因为所有点都在一侧，没有跨越）
        current_cut = 0.0
        
        # 记录每条超边目前在 Part 0 的节点数量
        nodes_in_part0 = np.zeros(len(self.hyperedges), dtype=int)
        
        best_cut = float('inf')
        best_split_idx = -1
        
        current_weight_part0 = 0.0
        
        # 扫描：将节点逐个从 Part 1 移入 Part 0
        for i in range(self.n - 1):
            node = order[i]
            current_weight_part0 += self.vertex_weights[node]
            
            # 更新此节点关联的超边状态
            for eid in self._inc[node]:
                deg = edge_degrees[eid]
                if deg <= 1:
                    continue
                
                # 移动前：nodes_in_part0[eid] 个点在 Part 0
                # 移动后：nodes_in_part0[eid] + 1 个点在 Part 0
                
                if nodes_in_part0[eid] == 0:
                    # 原本所有点在 Part 1，现在有 1 个进 Part 0 -> 变为 CUT
                    current_cut += self.hyperedge_weights[eid]
                elif nodes_in_part0[eid] == deg - 1:
                    # 原本 deg-1 个在 Part 0 (1 个在 Part 1)，现在所有点进 Part 0 -> 变为 UNCUT
                    current_cut -= self.hyperedge_weights[eid]
                
                nodes_in_part0[eid] += 1
            
            # 检查平衡约束
            if self.min_capacity <= current_weight_part0 <= self.max_capacity:
                if current_cut < best_cut:
                    best_cut = current_cut
                    best_split_idx = i
        
        # 构建最佳分区
        partition = np.ones(self.n, dtype=int)
        if best_split_idx != -1:
            partition[order[:best_split_idx + 1]] = 0
        else:
            # 如果没找到满足平衡的切割，强制中间切一刀
            mid = self.n // 2
            partition[order[:mid]] = 0
            # 这里 cut 可能不准确，重新计算一次作为保底
            best_cut = self._compute_cutsize(partition)

        return partition, best_cut

    def _compute_cutsize(self, partition):
        """辅助函数：计算给定分区的 cutsize"""
        part = np.asarray(partition, dtype=int)
        cut = 0.0
        for idx, hedge in enumerate(self.hyperedges):
            if len(hedge) <= 1:
                continue
            base = part[hedge[0]]
            for v in hedge[1:]:
                if part[v] != base:
                    cut += float(self.hyperedge_weights[idx])
                    break
        return float(cut)



# =============================================================================
# Part 2b: Julia SpecPart Interface (calls original SpectralRefinement.jl)
# =============================================================================

class JuliaSpecPartInterface:
    """Python <-> Julia bridge for original SpecPart implementation.

    This wrapper calls:
        SpectralRefinement.SpectralHmetisRefinement(...)

    Expected Julia repo layout:
        <repo_root>/
            SpecPart/
                SpectralRefinement.jl
                hmetis
                ilp_k_solver.py
                ...

    Notes:
    - We run each call inside an isolated workdir to avoid file name collisions
      (important when running in parallel).
    - We create a symlink named `SpecPart` inside the workdir pointing to the
      real repo's SpecPart directory, so Julia's relative calls like
      `python3 SpecPart/ilp_k_solver.py` and `./SpecPart/hmetis` keep working.
    """

    def __init__(
        self,
        spectral_refinement_jl: str = None,
        julia_cmd: str = None,
        keep_workdir: bool = False,
        weight_scale: int = 1000,
        verbose: bool = False,
    ):
        self.spectral_refinement_jl = spectral_refinement_jl or os.environ.get(
            "SPECPART_JL_PATH",
            DEFAULT_SPECPART_JL,
        )
        self.julia_cmd = julia_cmd or os.environ.get("JULIA_CMD", "julia")
        self.keep_workdir = bool(keep_workdir or (os.environ.get("SPECPART_KEEP_WORKDIR", "0") == "1"))
        self.weight_scale = int(os.environ.get("SPECPART_WEIGHT_SCALE", weight_scale))
        self.verbose = bool(verbose)

        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(self.spectral_refinement_jl), os.pardir))
        self.specpart_dir = os.path.join(self.repo_root, "SpecPart")

        if not os.path.isfile(self.spectral_refinement_jl):
            raise FileNotFoundError(f"SpectralRefinement.jl not found: {self.spectral_refinement_jl}")
        if not os.path.isdir(self.specpart_dir):
            raise FileNotFoundError(f"SpecPart dir not found under repo_root: {self.specpart_dir}")

    def _mk_workdir(self):
        base = os.environ.get("SPECPART_WORKDIR_BASE", None)
        if base:
            os.makedirs(base, exist_ok=True)
            workdir = tempfile.mkdtemp(prefix="specpart_julia_", dir=base)
        else:
            workdir = tempfile.mkdtemp(prefix="specpart_julia_")
        return workdir

    def _setup_workdir(self, workdir: str):
        link = os.path.join(workdir, "SpecPart")
        if not os.path.exists(link):
            os.symlink(self.specpart_dir, link)

    def _to_int_weights(self, weights):
        """hMETIS weights are typically integers. Convert float weights safely."""
        if weights is None:
            return None
        w = np.asarray(weights, dtype=float)
        if w.size == 0:
            return w.astype(int)
        # if already close to integers, just round
        if np.allclose(w, np.round(w), atol=1e-6):
            return np.round(w).astype(int)
        # otherwise scale up
        return np.maximum(1, np.round(w * float(self.weight_scale))).astype(int)

    def write_hmetis_hgr(
        self,
        filepath: str,
        num_vertices: int,
        hyperedges,
        vertex_weights=None,
        hyperedge_weights=None,
    ):
        """Write hypergraph in hMETIS .hgr format (1-indexed vertices)."""
        hyperedges = list(hyperedges)
        n = int(num_vertices)
        e = int(len(hyperedges))

        vw = self._to_int_weights(vertex_weights) if vertex_weights is not None else None
        hw = self._to_int_weights(hyperedge_weights) if hyperedge_weights is not None else None

        fmt = 0
        if hw is not None:
            fmt += 10
        if vw is not None:
            fmt += 1

        with open(filepath, "w") as f:
            if fmt == 0:
                f.write(f"{e} {n}\n")
            else:
                f.write(f"{e} {n} {fmt}\n")

            for i, hedge in enumerate(hyperedges):
                hedge = list(hedge)
                # filter degenerate
                if len(hedge) == 0:
                    continue
                if hw is not None:
                    f.write(str(int(hw[i])) + " ")
                f.write(" ".join(str(int(v) + 1) for v in hedge) + "\n")

            if vw is not None:
                for w in vw:
                    f.write(f"{int(w)}\n")

    def write_partition_file(self, filepath: str, part_vec):
        part_vec = np.asarray(part_vec, dtype=int).reshape(-1)
        with open(filepath, "w") as f:
            for p in part_vec:
                f.write(f"{int(p)}\n")

    def run_spectral_refinement(
        self,
        hgr_path: str,
        pfile_path: str,
        ub_factor: int = 10,
        seed: int = 0,
        nev: int = 2,
        refine_iters: int = 4,
        solver_iters: int = 20,
        cycles: int = 1,
        best_solns: int = 10,
        hyperedges_threshold: int = 900,
        extra_julia_args=None,
        hmetis_exec: str = DEFAULT_HMETIS_EXEC,
    ):
        """Call Julia SpectralRefinement.SpectralHmetisRefinement and return partition."""
        workdir = self._mk_workdir()
        self._setup_workdir(workdir)

        # run Julia in isolated workdir
        hg_abs = os.path.abspath(hgr_path)
        pf_abs = "" if (pfile_path is None or str(pfile_path).strip() == "") else os.path.abspath(pfile_path)

        # Julia code: include module, then run refinement
        # Use raw"..." to avoid escaping backslashes.
        pfile_literal = '""' if pf_abs == "" else f'raw"{pf_abs}"'
        julia_code = """include(raw"{jl}")
using .SpectralRefinement
SpectralRefinement.SpectralHmetisRefinement(
    hg="hg_xxx.hgr",     # 相对路径
    pfile="",            # 让 Julia 自己跑 hmetis
    Nparts=2,
    ub={ub},
    nev={nev},
    cycles={cycles},
    seed={seed},
    best_solns={best},
    refine_iters={rit},
    solver_iters={sit},
    hyperedges_threshold={het},
    pseed={seed},
    hmetis_exec=raw"{hmetis_exec}"
)
""".format(
            jl=self.spectral_refinement_jl,
            hg=hg_abs,
            pfile=pfile_literal,
            ub=int(ub_factor),
            nev=int(nev),
            cycles=int(cycles),
            seed=int(seed),
            best=int(best_solns),
            rit=int(refine_iters),
            sit=int(solver_iters),
            het=int(hyperedges_threshold),
            hmetis_exec=hmetis_exec,
        )

        cmd = [self.julia_cmd, "--color=no", "--startup-file=no", "-e", julia_code]
        if extra_julia_args:
            cmd = [self.julia_cmd] + list(extra_julia_args) + ["-e", julia_code]

        if self.verbose:
            print(f"    [JuliaSpecPart] workdir={workdir}")
            print(f"    [JuliaSpecPart] cmd={' '.join(cmd[:3])} ...")

        try:
            hg_for_julia = os.path.basename(hg_path)
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            # keep logs for debugging
            log_path = os.path.join(workdir, "julia_stderr.log")
            with open(log_path, "w") as f:
                f.write(e.stderr or "")
            raise RuntimeError(
                f"Julia SpecPart failed (see {log_path}).\nSTDERR:\n{(e.stderr or '')[:2000]}"
            ) from e

        # output partition path produced by SpectralHmetisRefinement
        hg_name = os.path.basename(hg_abs)
        out_part = os.path.join(workdir, f"{hg_name}_{int(ub_factor)}.part.2")
        if not os.path.isfile(out_part):
            # dump stdout/stderr for debugging
            out_log = os.path.join(workdir, "julia_stdout.log")
            err_log = os.path.join(workdir, "julia_stderr.log")
            with open(out_log, "w") as f:
                f.write(proc.stdout or "")
            with open(err_log, "w") as f:
                f.write(proc.stderr or "")
            raise FileNotFoundError(
                f"Julia finished but output partition not found: {out_part}. "
                f"Logs: {out_log}, {err_log}"
            )

        part = []
        with open(out_part, "r") as f:
            for ln in f:
                ln = ln.strip()
                if ln == "":
                    continue
                part.append(int(ln))
        part = np.asarray(part, dtype=int)

        # cleanup unless keep_workdir
        if not self.keep_workdir:
            try:
                shutil.rmtree(workdir)
            except Exception:
                pass

        return part


class SpecPartEngine:
    """SpecPart 主引擎（对齐 Step 4~7 + 最终对比）"""

    def __init__(self, hypergraph, x_features, y_features, vertex_weights=None, hyperedge_weights=None):
        self.n = int(hypergraph['num_vertices'])
        self.hyperedges = list(hypergraph['hyperedges'])
        self.x_features = np.asarray(x_features, dtype=float)
        self.y_features = np.asarray(y_features, dtype=float)
        self.eigenvectors = np.column_stack([self.x_features, self.y_features])

        self.vertex_weights = (
            np.asarray(vertex_weights, dtype=float) if vertex_weights is not None else np.ones(self.n, dtype=float)
        )
        self.hyperedge_weights = (
            list(hyperedge_weights) if hyperedge_weights is not None else [1.0] * len(self.hyperedges)
        )

        self.adj_matrix = self._build_clique_expansion()

    def _build_clique_expansion(self):
        """构建 clique expansion（树生成用），使用 2/net_size 归一化"""
        adj = lil_matrix((self.n, self.n))
        for he_idx, hedge in enumerate(self.hyperedges):
            weight = float(self.hyperedge_weights[he_idx])
            verts = list(hedge)
            net_size = len(verts)
            if net_size < 2:
                continue
            edge_weight = weight * 2.0 / net_size
            for i in range(len(verts)):
                for j in range(i + 1, len(verts)):
                    u = int(verts[i])
                    v = int(verts[j])
                    adj[u, v] += edge_weight
                    adj[v, u] += edge_weight
        return csr_matrix(adj)

    def _compute_cutsize(self, partition):
        part = np.asarray(partition, dtype=int)
        cut = 0.0
        for idx, hedge in enumerate(self.hyperedges):
            if len(hedge) <= 1:
                continue
            base = part[hedge[0]]
            for v in hedge[1:]:
                if part[v] != base:
                    cut += float(self.hyperedge_weights[idx])
                    break
        return float(cut)

    def _capacity_bounds(self, ub_factor):
        total = float(np.sum(self.vertex_weights))
        max_cap = float(np.ceil(total * (50.0 + ub_factor) / 100.0))
        min_cap = total - max_cap
        return min_cap, max_cap

    def _part_balance(self, partition):
        part = np.asarray(partition, dtype=int)
        w0 = float(np.sum(self.vertex_weights[part == 0]))
        w1 = float(np.sum(self.vertex_weights[part == 1]))
        return w0, w1

    def run(
        self,
        ub_factor=10,
        num_trees=5,
        best_solns=5,
        use_hmetis=False,
        hmetis_path="hmetis",
        clustered_hmetis_threshold=1000,
        verbose=True,
        # --- New / optional (does not break existing callers) ---
        backend=None,
        julia_seed=0,
        julia_nev=2,
        julia_refine_iters=4,
        julia_solver_iters=20,
        julia_cycles=1,
        julia_hyperedges_threshold=900,
    ):
        """Run SpecPart bipartition.

        默认使用 **Julia 原版 SpecPart** (SpectralRefinement.jl)。
        如 Julia 调用失败，会自动回退到本文件中保留的 Python 版本实现。

        Args:
            backend:
                - "julia" (default) : call original Julia SpecPart
                - "python"          : use legacy python re-implementation
                - None              : read from env SPECPART_BACKEND (default "julia")
        """
        backend = (backend or os.environ.get("SPECPART_BACKEND", "julia")).strip().lower()
        if backend == "python":
            return self._run_python_impl(
                ub_factor=ub_factor,
                num_trees=num_trees,
                best_solns=best_solns,
                use_hmetis=use_hmetis,
                hmetis_path=hmetis_path,
                clustered_hmetis_threshold=clustered_hmetis_threshold,
                verbose=verbose,
            )

        # Julia backend (preferred)
        try:
            return self._run_julia_impl(
                ub_factor=ub_factor,
                best_solns=best_solns,
                seed=julia_seed,
                nev=julia_nev,
                refine_iters=julia_refine_iters,
                solver_iters=julia_solver_iters,
                cycles=julia_cycles,
                hyperedges_threshold=julia_hyperedges_threshold,
                verbose=verbose,
            )
        except Exception as e:
            if verbose:
                print(f"    [SpecPartEngine] Julia backend failed: {e}")
                print("    [SpecPartEngine] Falling back to Python implementation ...")

            return self._run_python_impl(
                ub_factor=ub_factor,
                num_trees=num_trees,
                best_solns=best_solns,
                use_hmetis=use_hmetis,
                hmetis_path=hmetis_path,
                clustered_hmetis_threshold=clustered_hmetis_threshold,
                verbose=verbose,
            )

    def _make_hint_partition(self, ub_factor: int):
        """Generate an initial (hint) bipartition for Julia SpecPart.

        Julia 原版 SpectralHmetisRefinement 在 pfile 为空时会尝试跑外部 hmetis
        生成 hint。为了让 python 侧更可控、少依赖 PATH，这里默认用 GIFT 的
        x/y 特征做一次 sweep-cut 产生一个平衡的 hint partition。
        """
        hg_partitioner = HypergraphPartitioner(
            self.n, self.hyperedges, self.vertex_weights, self.hyperedge_weights, ub_factor
        )
        part_x, cut_x = hg_partitioner.partition_by_feature(self.x_features)
        part_y, cut_y = hg_partitioner.partition_by_feature(self.y_features)

        if float(cut_y) < float(cut_x):
            return np.asarray(part_y, dtype=int)
        return np.asarray(part_x, dtype=int)

    def _run_julia_impl(
        self,
        ub_factor=10,
        best_solns=5,
        seed=0,
        nev=2,
        refine_iters=4,
        solver_iters=20,
        cycles=1,
        hyperedges_threshold=900,
        verbose=True,
    ):
        """Julia SpecPart backend: call SpectralRefinement.jl and return (partition, cut)."""
        if verbose:
            print("    SpecPart Engine - Julia backend (SpectralRefinement.jl)")
            print(f"    Vertices: {self.n}, Hyperedges: {len(self.hyperedges)}")

        # 1) build temporary input files
        hint_mode = os.environ.get("SPECPART_HINT_MODE", "none").strip().lower()
        hint_part = None
        if hint_mode in ("sweep", "feature", "gift"):
            hint_part = self._make_hint_partition(int(ub_factor))

        iface = JuliaSpecPartInterface(
            spectral_refinement_jl=os.environ.get(
                "SPECPART_JL_PATH",
                DEFAULT_SPECPART_JL,
            ),
            julia_cmd=os.environ.get("JULIA_CMD", "julia"),
            verbose=bool(verbose and (os.environ.get("SPECPART_JULIA_VERBOSE", "0") == "1")),
        )

        workdir = self._mk_workdir()             # 你 Julia 实际运行的目录
        self._setup_workdir(workdir)             # 里面会准备 SpecPart symlink 等
        try:
            hg_path = os.path.join(workdir, f"hg_{uuid}.hgr")
            p_path = None
            if hint_part is not None:
                p_path = os.path.join(tmp_in_dir, "hint.part.2")

            iface.write_hmetis_hgr(
                filepath=hg_path,
                num_vertices=self.n,
                hyperedges=self.hyperedges,
                vertex_weights=self.vertex_weights,
                hyperedge_weights=self.hyperedge_weights,
            )
            if hint_part is not None:
                iface.write_partition_file(p_path, hint_part)

            # 2) run Julia
            part = iface.run_spectral_refinement(
                hgr_path=hg_path,
                pfile_path=p_path,
                ub_factor=int(ub_factor),
                seed=int(seed),
                nev=int(nev),
                refine_iters=int(refine_iters),
                solver_iters=int(solver_iters),
                cycles=int(cycles),
                best_solns=int(best_solns),
                hyperedges_threshold=int(hyperedges_threshold),
                hmetis_exec=DEFAULT_HMETIS_EXEC,
            )

        finally:
            # always remove inputs
            try:
                shutil.rmtree(tmp_in_dir)
            except Exception:
                pass

        part = np.asarray(part, dtype=int).reshape(-1)
        if part.size != self.n:
            raise ValueError(f"Julia partition size mismatch: got {part.size}, expected {self.n}")

        cut = float(self._compute_cutsize(part))
        return part.astype(int), cut


    def _run_python_impl(
        self,
        ub_factor=10,
        num_trees=5,
        best_solns=5,
        use_hmetis=False,
        hmetis_path="hmetis",
        clustered_hmetis_threshold=1000,
        verbose=True,
    ):
        """运行 SpecPart：补齐 Step4~7，返回最终最优二分 partition。

        Returns:
            final_partition (n,)
            final_cut (float)
        """
        if verbose:
            print("    SpecPart Engine - Using GIFT Features")
            print(f"    Vertices: {self.n}, Hyperedges: {len(self.hyperedges)}")

        # =====================
        # Step 1: 生成树
        # =====================
        t_step1 = time.time()
        tree_gen = TreeGenerator(self.adj_matrix, self.eigenvectors)
        trees = tree_gen.generate_all_trees(num_spt=max(1, num_trees - 2))
        t_step1 = time.time() - t_step1
        if verbose:
            print(f"    Generated {len(trees)} trees in {t_step1:.2f}s")

        # =====================
        # Step 2: 树分区 -> 候选池（cut pool）
        # =====================
        t_step2 = time.time()
        partition_list, cut_list = [], []
        if verbose:
            print("    Start Step 2: 树分区")

        for tree in trees:
            partitioner = TreePartitioner(tree, self.vertex_weights, ub_factor)
            for feat in (self.x_features, self.y_features):
                try:
                    part_vec, _tree_cut = partitioner.partition_by_eigenvector(feat)
                    hg_cut = self._compute_cutsize(part_vec)
                    partition_list.append(part_vec.astype(np.int8))
                    cut_list.append(float(hg_cut))
                except Exception:
                    continue

        # 如果树分区失败：回退到 hypergraph sweep baseline
        if len(partition_list) == 0:
            hg_partitioner = HypergraphPartitioner(
                self.n, self.hyperedges, self.vertex_weights, self.hyperedge_weights, ub_factor
            )
            base_part, base_cut = hg_partitioner.partition_by_feature(self.x_features)
            return base_part.astype(int), float(base_cut)

        partition_matrix = np.asarray(partition_list, dtype=np.int8)
        cuts = np.asarray(cut_list, dtype=float)
        unique_cnt = len({row.tobytes() for row in partition_matrix})
        if verbose:
            print(
                f"    [debug] Step2 candidates={partition_matrix.shape[0]}, unique={unique_cnt}, "
                f"cut(min/med/max)={cuts.min():.3f}/{np.median(cuts):.3f}/{cuts.max():.3f}"
            )
            t_step2 = time.time() - t_step2
            print(f"    End Step 2: 树分区 ({t_step2:.2f}s)")

        # =====================
        # Step 3: Cut-Overlay 聚类 (SpecPart方式)
        # =====================
        t_step3 = time.time()
        overlay = CutOverlayClustering(self.n, self.hyperedges, self.hyperedge_weights, self.vertex_weights)
        best_part_matrix, best_cuts = overlay.select_best_partitions(
            partition_matrix, cuts, top_k=best_solns, dedup=True
        )

        # global best in pool
        global_part = best_part_matrix[0].astype(int)
        global_cut = float(best_cuts[0])

        clusters, cluster_map, cluster_sizes, _cut_union = overlay.cut_overlay_clustering(best_part_matrix)
        if verbose:
            ones = int(np.sum(cluster_sizes == 1))
            mx = int(cluster_sizes.max()) if cluster_sizes.size > 0 else 0
            t_step3 = time.time() - t_step3
            print(
                f"    Step3 Cut-Overlay: clusters={len(clusters)}, "
                f"dust(size=1)={ones} ({(ones/max(1,len(clusters)))*100:.1f}%), max_cluster={mx} ({t_step3:.2f}s)"
            )

        # =====================
        # Step 4: Partition Clustered Hypergraph
        # =====================
        t_step4 = time.time()
        new_hyperedges, new_weights, cluster_weights = overlay.generate_clustered_hypergraph(clusters, cluster_map)

        tool_part_full = None
        tool_cut_full = float('inf')

        if len(clusters) <= 1:
            # 没有可分的 super-nodes
            tool_part_full = global_part
            tool_cut_full = global_cut
        else:
            # 对 cluster-hypergraph 做二分
            clustered_partitioner = HypergraphPartitioner(
                len(clusters), new_hyperedges, cluster_weights, new_weights, ub_factor
            )

            cluster_partition = None
            cluster_cut = float('inf')

            # 优先 hMETIS（如果配置且规模不大）
            if use_hmetis and len(clusters) < int(clustered_hmetis_threshold) and len(new_hyperedges) > 0:
                cluster_partition, cluster_cut = clustered_partitioner.run_hmetis(
                    hmetis_path=hmetis_path, num_parts=2, nruns=10
                )

            # fallback: feature-sweep（尝试 mean-x 与 mean-y 两个排序，取更优）
            if cluster_partition is None:
                cluster_mean_x = np.asarray([float(np.mean(self.x_features[c])) for c in clusters], dtype=float)
                cluster_mean_y = np.asarray([float(np.mean(self.y_features[c])) for c in clusters], dtype=float)

                part_x, cut_x = clustered_partitioner.partition_by_feature(cluster_mean_x)
                part_y, cut_y = clustered_partitioner.partition_by_feature(cluster_mean_y)

                if cut_y < cut_x:
                    cluster_partition, cluster_cut = part_y, cut_y
                else:
                    cluster_partition, cluster_cut = part_x, cut_x

            # Step 6: Map back to original vertices
            cluster_partition = np.asarray(cluster_partition, dtype=int)
            cluster_map = np.asarray(cluster_map, dtype=int)
            tool_part_full = cluster_partition[cluster_map]
            tool_cut_full = float(self._compute_cutsize(tool_part_full))

            if verbose:
                t_step4 = time.time() - t_step4
                print(
                    f"    Step4 clustered-HG: superV={len(clusters)}, superE={len(new_hyperedges)}, "
                    f"clustered_cut(hg_cc)={float(cluster_cut):.3f}, mapped_cut(orig)={tool_cut_full:.3f} ({t_step4:.2f}s)"
                )

        # =====================
        # Step 5: Compare & pick best (pool best vs clustered-hg best)
        # =====================
        if tool_cut_full < global_cut:
            chosen_part = np.asarray(tool_part_full, dtype=int)
            chosen_cut = float(tool_cut_full)
            chosen_src = 'clustered-hg'
        else:
            chosen_part = np.asarray(global_part, dtype=int)
            chosen_cut = float(global_cut)
            chosen_src = 'cut-pool'

        # =====================
        # Step 7: Final compare vs baseline (hMETIS or sweep)
        # =====================
        baseline_part = None
        baseline_cut = float('inf')

        hg_partitioner = HypergraphPartitioner(
            self.n, self.hyperedges, self.vertex_weights, self.hyperedge_weights, ub_factor
        )

        if use_hmetis:
            print(f"Running hmetis with path: {hmetis_path}")
            baseline_part, baseline_cut = hg_partitioner.run_hmetis(
                hmetis_path=hmetis_path, num_parts=2, nruns=10
            )

        if baseline_part is None:
            baseline_part, baseline_cut = hg_partitioner.partition_by_feature(self.x_features)

        baseline_part = np.asarray(baseline_part, dtype=int)
        baseline_cut = float(self._compute_cutsize(baseline_part))

        if chosen_cut >= baseline_cut:
            final_part = baseline_part
            final_cut = baseline_cut
            final_src = 'baseline'
        else:
            final_part = chosen_part
            final_cut = chosen_cut
            final_src = chosen_src

        if verbose:
            min_cap, max_cap = self._capacity_bounds(ub_factor)
            w0, w1 = self._part_balance(final_part)
            ok = (min_cap <= w0 <= max_cap) and (min_cap <= w1 <= max_cap)
            print(
                f"    Step5/7 pick: src={final_src}, cut={final_cut:.3f}, "
                f"balance={w0:.1f}/{w1:.1f}, ok={ok}"
            )

        return final_part.astype(int), float(final_cut)


# =============================================================================
# Part 3: 完整Pipeline集成
# =============================================================================
# =============================================================================
# Part 3: 完整Pipeline集成
# =============================================================================

class GIFTSpecPartPipeline:
    """完整的 GIFT+SpecPart 集成 Pipeline + 递归二分聚类"""

    def __init__(self):
        self.results = {}

    def run_on_cluster(
        self,
        adj_matrix,
        hyperedges,
        node_indices,
        ub_factor=10,
        gift_scale=0.5,
        use_mixed_filter=True,
        num_trees=5,
        best_solns=5,
        use_hmetis=False,
        hmetis_path="hmetis",
        verbose=True,
    ):
        """对单个 cluster 运行 GIFT + SpecPart（二分）"""
        n = adj_matrix.shape[0]

        if verbose:
            print(f"\n  Processing cluster with {n} nodes, {len(hyperedges)} hyperedges")

        # Step 1: GIFT 布局
        if verbose:
            print("  [1] Running GIFT layout...")

        gift = GIFTInterface(adj_matrix)
        positions = gift.run_gift_layout(scale=gift_scale, use_mixed_filter=use_mixed_filter)
        x_features, y_features = gift.get_xy_features(positions)

        # Step 2: SpecPart 二分
        if verbose:
            print("  [2] Running SpecPart (with Step4~7)...")

        hypergraph = {'num_vertices': n, 'hyperedges': hyperedges}
        engine = SpecPartEngine(hypergraph, x_features, y_features)
        partition, cutsize = engine.run(
            ub_factor=ub_factor,
            num_trees=num_trees,
            best_solns=best_solns,
            use_hmetis=use_hmetis,
            hmetis_path=hmetis_path,
            verbose=verbose,
        )

        # 这里的 partition 是局部索引(0..n-1) 的 0/1；node_indices 用于你外层映射回全局
        return partition, cutsize, positions

    def export_results(self, output_dir, design_name, partition, positions, node_indices, hyperedges):
        """导出结果"""
        os.makedirs(output_dir, exist_ok=True)

        # 导出分区
        part_file = os.path.join(output_dir, f"{design_name}_partition.txt")
        with open(part_file, 'w') as f:
            for p in partition:
                f.write(f"{int(p)}\n")

        # 导出位置
        pos_file = os.path.join(output_dir, f"{design_name}_positions.txt")
        np.savetxt(pos_file, positions, fmt='%.6f')

        # 导出超图 (hMETIS格式)
        hg_file = os.path.join(output_dir, f"{design_name}.hgr")
        with open(hg_file, 'w') as f:
            f.write(f"{len(hyperedges)} {len(node_indices)}\n")
            for hedge in hyperedges:
                f.write(' '.join(str(int(v) + 1) for v in hedge) + '\n')

        config = {
            'num_vertices': len(node_indices),
            'num_hyperedges': len(hyperedges),
            'partition_file': part_file,
            'positions_file': pos_file,
            'hypergraph_file': hg_file,
            'cutsize': int(self._compute_cutsize(partition, hyperedges)),
        }

        config_file = os.path.join(output_dir, f"{design_name}_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"  Results exported to {output_dir}")
        return config

    def _compute_cutsize(self, partition, hyperedges):
        cut = 0
        for hedge in hyperedges:
            if len(set(partition[v] for v in hedge)) > 1:
                cut += 1
        return cut

    # ============================
    # Recursive bisection clustering
    # ============================
    def _induce_subhypergraph(self, hyperedges, subset_idx):
        """诱导子超图：将 hyperedges 限制在 subset_idx 内，并重编号为 0..k-1"""
        subset_idx = list(map(int, subset_idx))
        subset_set = set(subset_idx)
        old_to_new = {old: new for new, old in enumerate(subset_idx)}

        edge_map = defaultdict(float)
        for hedge in hyperedges:
            # 取交集（保留在该 part 内的 pin）
            new_verts = [old_to_new[v] for v in hedge if int(v) in subset_set]
            if len(new_verts) < 2:
                continue
            key = tuple(sorted(set(new_verts)))
            if len(key) < 2:
                continue
            edge_map[key] += 1.0

        new_edges = list(edge_map.keys())
        # 目前权重未向外暴露（需要可扩展）
        return new_edges

    def recursive_bisection_clustering(
        self,
        adj_matrix,
        hyperedges,
        node_indices,
        ub_factor=10,
        gift_scale=0.5,
        use_mixed_filter=True,
        num_trees=5,
        best_solns=5,
        use_hmetis=False,
        hmetis_path=DEFAULT_HMETIS_EXEC,
        min_cluster_size=50,
        max_depth=10,
        depth=0,
        positions=None,
        reuse_parent_positions=True,
        verbose=False,
        random_seed=0,
    ):
        """递归二分得到多簇聚类结果 — 调用一次 Julia RecursiveBisection.jl 完成全部递归。

        Returns:
            clusters: List[List[global_node_id]]
        """
        n = len(node_indices)

        # stop criteria
        if n <= int(min_cluster_size) or len(hyperedges) == 0:
            return [list(node_indices)]

        # --- 写超图到临时文件 (hMETIS 格式, 1-indexed) ---
        workdir = tempfile.mkdtemp(prefix="recbisect_julia_")
        hgr_path = os.path.join(workdir, "input.hgr")
        output_json = os.path.join(workdir, "clusters.json")

        try:
            with open(hgr_path, "w") as f:
                f.write(f"{len(hyperedges)} {n}\n")
                for hedge in hyperedges:
                    f.write(" ".join(str(int(v) + 1) for v in hedge) + "\n")

            # --- 调用 Julia RecursiveBisection.jl ---
            recursive_jl = os.environ.get(
                "RECURSIVE_BISECTION_JL",
                DEFAULT_RECURSIVE_BISECTION_JL,
            )
            julia_cmd = os.environ.get("JULIA_CMD", "julia")

            cmd = [
                julia_cmd,
                "--color=no",
                "--startup-file=no",
                recursive_jl,
                "--hgr", hgr_path,
                "--output", output_json,
                "--ub", str(int(ub_factor)),
                "--best_solns", str(int(best_solns)),
                "--seed", str(int(random_seed)),
                "--min_cluster_size", str(int(min_cluster_size)),
                "--max_depth", str(int(max_depth)),
                "--hmetis_path", str(hmetis_path),
            ]
            if verbose:
                cmd.append("--verbose")

            if verbose:
                print(f"    [RecursiveBisection] Calling Julia once: n={n}, hedges={len(hyperedges)}, seed={random_seed}")

            proc = subprocess.Popen(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                # Kill entire process group (Julia + hmetis children)
                import signal
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait()
                print(f"    [RecursiveBisection] Julia timed out (600s), returning single cluster")
                return [list(node_indices)]

            if verbose and stdout:
                for line in stdout.strip().split("\n")[-20:]:
                    print(f"    [Julia] {line}")

            if proc.returncode != 0:
                err_msg = (stderr or "")[:2000]
                print(f"    [RecursiveBisection] Julia failed (rc={proc.returncode}): {err_msg}")
                return [list(node_indices)]

            # --- 解析 JSON 输出 ---
            if not os.path.isfile(output_json):
                print(f"    [RecursiveBisection] Output JSON not found: {output_json}")
                return [list(node_indices)]

            with open(output_json, "r") as f:
                result = json.load(f)

            julia_clusters = result.get("clusters", [])
            if not julia_clusters:
                return [list(node_indices)]

            # Julia 输出是 1-based 局部索引 → 转为 0-based → 映射到全局 node_indices
            clusters_out = []
            for jc in julia_clusters:
                global_ids = [node_indices[int(v) - 1] for v in jc if 1 <= int(v) <= n]
                if global_ids:
                    clusters_out.append(global_ids)

            if not clusters_out:
                return [list(node_indices)]

            if verbose:
                print(f"    [RecursiveBisection] Got {len(clusters_out)} clusters from Julia")

            return clusters_out

        except Exception as e:
            print(f"    [RecursiveBisection] Error: {e}, returning single cluster")
            return [list(node_indices)]
        finally:
            try:
                shutil.rmtree(workdir)
            except Exception:
                pass

    @staticmethod
    def batch_recursive_bisection(
        cluster_jobs,
        ub_factor=10,
        best_solns=10,
        min_cluster_size=50,
        max_depth=10,
        hmetis_path=DEFAULT_HMETIS_EXEC,
        verbose=False,
        timeout=1800,
        num_seeds=1,
    ):
        """Batch-process multiple clusters in a single Julia session to avoid JIT overhead.

        Args:
            cluster_jobs: list of dicts, each with:
                - 'hyperedges': list of tuples (0-based local indices)
                - 'num_vertices': int
                - 'node_indices': list of global node ids
                - 'random_seed': int (optional)
            ub_factor, best_solns, min_cluster_size, max_depth, hmetis_path: SpecPart params
            verbose: print progress
            timeout: max seconds for the entire batch Julia process

        Returns:
            list of cluster results, one per job. Each result is a list of clusters
            (list of lists of global node ids).
        """
        if not cluster_jobs:
            return []

        workdir = tempfile.mkdtemp(prefix="batch_specpart_")
        manifest_path = os.path.join(workdir, "manifest.json")
        jobs_for_manifest = []
        job_meta = []  # track (num_vertices, node_indices) per job

        try:
            for idx, job in enumerate(cluster_jobs):
                hyperedges = job['hyperedges']
                n = job['num_vertices']
                node_indices = job['node_indices']
                seed = job.get('random_seed', 0)

                # Skip trivially small clusters
                if n <= min_cluster_size or len(hyperedges) == 0:
                    job_meta.append({
                        'n': n,
                        'node_indices': node_indices,
                        'skip': True,
                    })
                    jobs_for_manifest.append(None)
                    continue

                # Write hgr file
                hgr_path = os.path.join(workdir, f"cluster_{idx}.hgr")
                output_path = os.path.join(workdir, f"cluster_{idx}_result.json")

                with open(hgr_path, "w") as f:
                    f.write(f"{len(hyperedges)} {n}\n")
                    for hedge in hyperedges:
                        f.write(" ".join(str(int(v) + 1) for v in hedge) + "\n")

                jobs_for_manifest.append({
                    "hgr_path": hgr_path,
                    "output_path": output_path,
                    "seed": seed,
                    "min_cluster_size": min_cluster_size,
                    "max_depth": max_depth,
                    "ub": ub_factor,
                    "best_solns": best_solns,
                    "hmetis_path": hmetis_path,
                    "num_seeds": num_seeds,
                })
                job_meta.append({
                    'n': n,
                    'node_indices': node_indices,
                    'skip': False,
                    'output_path': output_path,
                })

            # Build manifest (only non-skipped jobs)
            manifest_jobs = [j for j in jobs_for_manifest if j is not None]

            if not manifest_jobs:
                # All jobs were skipped (too small)
                results = []
                for meta in job_meta:
                    results.append([list(meta['node_indices'])])
                return results

            manifest = {"jobs": manifest_jobs}
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            # Call Julia in batch mode
            recursive_jl = os.environ.get(
                "RECURSIVE_BISECTION_JL",
                DEFAULT_RECURSIVE_BISECTION_JL,
            )
            julia_cmd = os.environ.get("JULIA_CMD", "julia")

            cmd = [
                julia_cmd,
                "--color=no",
                "--startup-file=no",
                recursive_jl,
                "--batch", manifest_path,
            ]
            if verbose:
                cmd.append("--verbose")

            if verbose:
                print(f"    [BatchSpecPart] Launching Julia batch: {len(manifest_jobs)} jobs")

            import signal
            proc = subprocess.Popen(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait()
                print(f"    [BatchSpecPart] Julia timed out ({timeout}s), {len(job_meta)} jobs fallback")
                # Return single-cluster fallback for all jobs
                return [[list(meta['node_indices'])] for meta in job_meta]

            if verbose and stdout:
                for line in stdout.strip().split("\n")[-10:]:
                    print(f"    [Julia] {line}")

            if proc.returncode != 0:
                err_msg = (stderr or "")[:2000]
                print(f"    [BatchSpecPart] Julia failed (rc={proc.returncode}): {err_msg}")
                return [[list(meta['node_indices'])] for meta in job_meta]

            # Parse results
            results = []
            diag_single = 0
            diag_multi = 0
            for meta in job_meta:
                if meta['skip']:
                    results.append([list(meta['node_indices'])])
                    continue

                output_path = meta['output_path']
                node_indices = meta['node_indices']
                n = meta['n']

                if not os.path.isfile(output_path):
                    print(f"    [BatchSpecPart] WARNING: missing output for n={n}")
                    results.append([list(node_indices)])
                    continue

                try:
                    with open(output_path, "r") as f:
                        result = json.load(f)

                    julia_clusters = result.get("clusters", [])
                    if not julia_clusters:
                        results.append([list(node_indices)])
                        continue

                    # Julia outputs 1-based local indices -> map to global
                    clusters_out = []
                    for jc in julia_clusters:
                        global_ids = [node_indices[int(v) - 1] for v in jc if 1 <= int(v) <= n]
                        if global_ids:
                            clusters_out.append(global_ids)

                    final = clusters_out if clusters_out else [list(node_indices)]
                    results.append(final)
                    if len(final) <= 1:
                        diag_single += 1
                    else:
                        diag_multi += 1
                except Exception as e:
                    print(f"    [BatchSpecPart] Failed to parse {output_path}: {e}")
                    results.append([list(node_indices)])

            if verbose:
                print(f"    [BatchSpecPart] Results: {diag_multi} split, {diag_single} single-cluster")

            return results

        except Exception as e:
            print(f"    [BatchSpecPart] Error: {e}")
            import traceback
            traceback.print_exc()
            return [[list(job['node_indices'])] for job in cluster_jobs]
        finally:
            try:
                shutil.rmtree(workdir)
            except Exception:
                pass

    @staticmethod
    def batch_k_specpart(
        cluster_jobs,
        ub_factor=10,
        best_solns=10,
        min_cluster_size=50,
        verbose=False,
        timeout=1800,
        num_workers=4,
        specpart_mode="gift_single",
        per_job_timeout=120,
    ):
        """Batch-process multiple clusters via K_SpecPart direct K-way partitioning.

        Args:
            cluster_jobs: list of dicts, each with:
                - 'hyperedges': list of tuples (0-based local indices)
                - 'num_vertices': int
                - 'node_indices': list of global node ids
                - 'num_parts': int (K for this cluster)
                - 'random_seed': int (optional)
                - 'positions': np.ndarray (n×2, optional GIFT coordinates)
            ub_factor, best_solns, min_cluster_size: SpecPart params
            verbose: print progress
            timeout: max seconds for each parallel sub-batch Julia process
            num_workers: max number of parallel Julia processes

        Returns:
            list of cluster results, one per job. Each result is a list of clusters
            (list of lists of global node ids).
        """
        if not cluster_jobs:
            return []

        workdir = tempfile.mkdtemp(prefix="batch_k_specpart_")
        jobs_for_manifest = []
        job_meta = []

        try:
            # --- Phase 1: prepare all hgr / features files ---
            for idx, job in enumerate(cluster_jobs):
                hyperedges = job['hyperedges']
                n = job['num_vertices']
                node_indices = job['node_indices']
                num_parts = job.get('num_parts', 2)
                seed = job.get('random_seed', 0)

                # Skip trivially small clusters
                if n <= min_cluster_size or len(hyperedges) == 0:
                    job_meta.append({
                        'n': n,
                        'node_indices': node_indices,
                        'skip': True,
                    })
                    jobs_for_manifest.append(None)
                    continue

                hgr_path = os.path.join(workdir, f"cluster_{idx}.hgr")
                output_path = os.path.join(workdir, f"cluster_{idx}_result.json")

                with open(hgr_path, "w") as f:
                    f.write(f"{len(hyperedges)} {n}\n")
                    for hedge in hyperedges:
                        f.write(" ".join(str(int(v) + 1) for v in hedge) + "\n")

                # Write GIFT features file if positions are available
                features_file = ""
                positions = job.get('positions', None)
                if positions is not None:
                    positions = np.asarray(positions, dtype=float)
                    if positions.shape[0] == n and positions.shape[1] >= 2:
                        features_path = os.path.join(workdir, f"cluster_{idx}_features.txt")
                        # Add tiny jitter to break coordinate ties;
                        # avoids span==0 → 1/span^2 overflow in Julia
                        # tree_partition reweigh_graph, which causes
                        # BoundsError on degenerate trees.
                        feat = positions[:, :2].copy()
                        feat_range = feat.ptp(axis=0)
                        feat_range = np.where(feat_range > 0, feat_range, 1.0)
                        jitter_rng = np.random.RandomState(seed & 0xFFFFFFFF)
                        feat += jitter_rng.uniform(-1e-6, 1e-6, size=feat.shape) * feat_range
                        np.savetxt(features_path, feat, fmt="%.8f")
                        features_file = features_path

                manifest_job = {
                    "hgr_path": hgr_path,
                    "output_path": output_path,
                    "num_parts": num_parts,
                    "seed": seed,
                    "imb": ub_factor,
                    "best_solns": best_solns,
                    "specpart_mode": specpart_mode,
                }
                if features_file:
                    manifest_job["features_file"] = features_file

                jobs_for_manifest.append(manifest_job)
                job_meta.append({
                    'n': n,
                    'node_indices': node_indices,
                    'skip': False,
                    'output_path': output_path,
                })

            manifest_jobs = [j for j in jobs_for_manifest if j is not None]

            if not manifest_jobs:
                results = []
                for meta in job_meta:
                    results.append([list(meta['node_indices'])])
                return results

            # --- Phase 2: split into parallel sub-batches ---
            k_specpart_jl = os.environ.get(
                "K_SPECPART_JL",
                DEFAULT_K_SPECPART_JL,
            )
            julia_cmd = os.environ.get("JULIA_CMD", "julia")

            # Determine number of parallel Julia workers
            # Each Julia process has ~60s startup overhead, so don't spawn too many
            n_workers = min(num_workers, max(1, len(manifest_jobs) // 20))
            chunk_size = (len(manifest_jobs) + n_workers - 1) // n_workers
            chunks = [manifest_jobs[i:i+chunk_size]
                      for i in range(0, len(manifest_jobs), chunk_size)]
            n_workers = len(chunks)  # actual number of chunks
            # Scale sub-batch timeout: per_job_timeout * jobs_in_chunk + Julia startup overhead
            effective_timeout = max(timeout, int(per_job_timeout * chunk_size + 180))

            if verbose:
                print(f"    [K_SpecPart] Launching {n_workers} parallel Julia batches, "
                      f"{len(manifest_jobs)} jobs total "
                      f"(~{chunk_size} jobs/worker, sub-batch timeout={effective_timeout}s, "
                      f"per_job_timeout={per_job_timeout}s)")

            import signal
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _run_sub_batch(chunk_idx, chunk):
                """Launch one Julia process for a chunk of jobs."""
                sub_cwd = os.path.join(workdir, f"sub_{chunk_idx}")
                os.makedirs(sub_cwd, exist_ok=True)
                sub_manifest = os.path.join(sub_cwd, "manifest.json")
                with open(sub_manifest, "w") as mf:
                    json.dump({"jobs": chunk, "per_job_timeout": per_job_timeout}, mf, indent=2)

                cmd = [
                    julia_cmd,
                    "--color=no",
                    "--startup-file=no",
                    k_specpart_jl,
                    "--batch", sub_manifest,
                ]

                # Write stderr to file so we can inspect progress even if process times out
                stderr_log = os.path.join(sub_cwd, "stderr.log")
                stderr_fh = open(stderr_log, "w")
                proc = subprocess.Popen(
                    cmd,
                    cwd=sub_cwd,
                    stdout=subprocess.PIPE,
                    stderr=stderr_fh,
                    text=True,
                    start_new_session=True,
                )
                try:
                    stdout, _ = proc.communicate(timeout=effective_timeout)
                    stderr_fh.close()
                    stderr = open(stderr_log).read()
                    return chunk_idx, proc.returncode, stdout, stderr, False
                except subprocess.TimeoutExpired:
                    stderr_fh.close()
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    proc.wait()
                    # Read whatever stderr was written before timeout
                    stderr = ""
                    try:
                        stderr = open(stderr_log).read()
                        # Count how many jobs completed before timeout
                        completed = stderr.count("completed in")
                        total = len(chunk)
                        print(f"    [K_SpecPart] Sub-batch {chunk_idx} timed out ({effective_timeout}s): "
                              f"{completed}/{total} jobs completed before kill")
                    except Exception:
                        pass
                    return chunk_idx, -1, "", stderr, True

            # Launch all sub-batches in parallel
            timed_out_chunks = set()
            failed_chunks = set()
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = {
                    executor.submit(_run_sub_batch, ci, chunk): ci
                    for ci, chunk in enumerate(chunks)
                }
                for future in as_completed(futures):
                    ci = futures[future]
                    try:
                        chunk_idx, rc, stdout, stderr, timed_out = future.result()
                        if timed_out:
                            timed_out_chunks.add(chunk_idx)
                            if verbose:
                                print(f"    [K_SpecPart] Sub-batch {chunk_idx} timed out "
                                      f"({effective_timeout}s), {len(chunks[chunk_idx])} jobs fallback")
                        elif rc != 0:
                            failed_chunks.add(chunk_idx)
                            if verbose:
                                err_msg = (stderr or "")[:500]
                                print(f"    [K_SpecPart] Sub-batch {chunk_idx} failed "
                                      f"(rc={rc}): {err_msg}")
                        else:
                            if verbose and stderr:
                                stderr_lines = stderr.strip().split("\n")
                                error_lines = [l for l in stderr_lines if any(kw in l for kw in
                                    ["Error", "error", "EXCEPTION", "Exception", "exception",
                                     "FAILED", "failed",
                                     "hmetis-fallback", "DimensionMismatch", "BoundsError",
                                     "MethodError", "ArgumentError", "UndefVarError"])]
                                if error_lines:
                                    print(f"    [Julia sub-batch {chunk_idx}] "
                                          f"=== ERRORS ({len(error_lines)}) ===")
                                    for line in error_lines[:5]:
                                        print(f"    [Julia stderr] {line}")
                                print(f"    [Julia sub-batch {chunk_idx}] "
                                      f"({len(stderr_lines)} lines total, last 5):")
                                for line in stderr_lines[-5:]:
                                    print(f"    [Julia stderr] {line}")
                    except Exception as exc:
                        failed_chunks.add(ci)
                        if verbose:
                            print(f"    [K_SpecPart] Sub-batch {ci} exception: {exc}")

            if verbose:
                ok = n_workers - len(timed_out_chunks) - len(failed_chunks)
                print(f"    [K_SpecPart] Sub-batches done: {ok} ok, "
                      f"{len(timed_out_chunks)} timed-out, {len(failed_chunks)} failed")

            # --- Phase 3: parse results ---
            results = []
            diag_single = 0
            diag_multi = 0
            for meta in job_meta:
                if meta['skip']:
                    results.append([list(meta['node_indices'])])
                    continue

                output_path = meta['output_path']
                node_indices = meta['node_indices']
                n = meta['n']

                if not os.path.isfile(output_path):
                    results.append([list(node_indices)])
                    diag_single += 1
                    continue

                try:
                    with open(output_path, "r") as f:
                        result = json.load(f)

                    julia_clusters = result.get("clusters", [])
                    if not julia_clusters:
                        results.append([list(node_indices)])
                        diag_single += 1
                        continue

                    # Julia outputs 1-based local indices -> map to global
                    clusters_out = []
                    for jc in julia_clusters:
                        global_ids = [node_indices[int(v) - 1] for v in jc
                                      if 1 <= int(v) <= n]
                        if global_ids:
                            clusters_out.append(global_ids)

                    final = clusters_out if clusters_out else [list(node_indices)]
                    results.append(final)
                    if len(final) <= 1:
                        diag_single += 1
                    else:
                        diag_multi += 1
                except Exception as e:
                    if verbose:
                        print(f"    [K_SpecPart] Failed to parse {output_path}: {e}")
                    results.append([list(node_indices)])
                    diag_single += 1

            if verbose:
                print(f"    [K_SpecPart] Results: {diag_multi} split, "
                      f"{diag_single} single-cluster")

            return results

        except Exception as e:
            print(f"    [K_SpecPart] Error: {e}")
            import traceback
            traceback.print_exc()
            return [[list(job['node_indices'])] for job in cluster_jobs]
        finally:
            try:
                shutil.rmtree(workdir)
            except Exception:
                pass


# =============================================================================
# 测试代码
# =============================================================================
# =============================================================================
# 测试代码
# =============================================================================

def test_complete_pipeline():
    """测试完整Pipeline"""
    np.random.seed(42)
    
    # 创建测试数据
    n = 200
    num_hedges = 100
    
    # 创建邻接矩阵 (两个cluster)
    adj = lil_matrix((n, n))
    for _ in range(300):
        if np.random.rand() < 0.7:
            # 同一cluster内的边
            if np.random.rand() < 0.5:
                i, j = np.random.choice(n//2, 2, replace=False)
            else:
                i, j = np.random.choice(range(n//2, n), 2, replace=False)
        else:
            # 跨cluster的边
            i = np.random.choice(n//2)
            j = np.random.choice(range(n//2, n))
        adj[i, j] = adj[j, i] = 1
    
    adj = csr_matrix(adj)
    
    # 创建超边
    hyperedges = []
    for _ in range(num_hedges):
        size = np.random.randint(2, 6)
        hedge = tuple(np.random.choice(n, size=size, replace=False))
        hyperedges.append(hedge)
    
    node_indices = list(range(n))
    
    # 运行Pipeline
    pipeline = GIFTSpecPartPipeline()
    partition, cutsize, positions = pipeline.run_on_cluster(
        adj_matrix=adj,
        hyperedges=hyperedges,
        node_indices=node_indices,
        ub_factor=10,
        gift_scale=0.5,
        use_mixed_filter=True,
        num_trees=5,
        best_solns=5,
        use_hmetis=False,
        verbose=True
    )
    
    print(f"\n{'='*60}")
    print("Test Results:")
    print(f"  Partition distribution: {np.bincount(partition)}")
    print(f"  Cutsize: {cutsize}")
    print(f"  Position range: X=[{positions[:,0].min():.2f}, {positions[:,0].max():.2f}], "
          f"Y=[{positions[:,1].min():.2f}, {positions[:,1].max():.2f}]")
    print(f"{'='*60}")


if __name__ == "__main__":
    test_complete_pipeline()
