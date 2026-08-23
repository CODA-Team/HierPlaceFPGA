"""
FPGA Clustering Pipeline: Louvain -> GIFT -> SpecPart
=====================================================
"""
from __future__ import annotations

import os
import re
import time
import numpy as np
from scipy.sparse import csc_matrix, lil_matrix, identity, coo_matrix, diags
from scipy.sparse import csgraph, linalg as sp_linalg
from collections import defaultdict
from multiprocessing import Pool
import json
from typing import Optional


# =============================================================================
# 第一部分: GIFT算法实现 (从原始代码提取)
# =============================================================================

class GiFt:

    def __init__(self, adj_mat):
        """
        初始化GIFT
        
        Args:
            adj_mat: 邻接矩阵 (scipy sparse matrix)
        """
        self.adj_mat = adj_mat
        self.norm_adj = None
        self.d_mat = None
        self.smallest_eigenvalue = None
        
    def train(self, sigma):
        """
        训练滤波器: 计算归一化邻接矩阵
        
        公式: norm_adj = D^{-0.5} (A + σI) D^{-0.5}
        
        Args:
            sigma: 增广参数 (控制低通/高通特性)
        """
        adj_mat = self.adj_mat
        adj_mat = csc_matrix(adj_mat)
        dim = adj_mat.shape[0]
        
        start = time.time()
        adj_mat = adj_mat + sigma * identity(dim)  # augmented adj: A + σI
        rowsum = np.array(adj_mat.sum(axis=1)).flatten()
        d_inv = np.power(rowsum, -0.5)
        d_inv[np.isinf(d_inv)] = 0.
        d_mat = diags(d_inv)  # D^{-0.5}
        
        norm_adj = d_mat.dot(adj_mat)
        norm_adj = norm_adj.dot(d_mat)
        
        self.norm_adj = norm_adj  # D^{-0.5}(A+σI)D^{-0.5}
        self.d_mat = d_mat
        
        end = time.time()
        # print(f'GIFT train time: {end - start:.3f}s')
        
    def new_filter_train(self):
        """
        替代滤波器训练方法 (基于拉普拉斯)
        
        公式: norm_adj = (λ_max * I - L) / λ_max
        """
        adj_mat = self.adj_mat
        adj_mat = csc_matrix(adj_mat)
        dim = adj_mat.shape[0]
        
        d_mat = diags(np.array(adj_mat.sum(axis=1)).flatten())  # D
        L = d_mat - adj_mat  # L = D - A
        L = csc_matrix(L)
        
        # 使用Gershgorin圆盘估计λ_max
        diag_L = L.diagonal()
        row_sum = np.abs(L).sum(axis=1).A1
        R_Gershgorin = row_sum - np.abs(diag_L)
        lambda_max = np.max(diag_L + R_Gershgorin)
        
        norm_adj = (lambda_max * identity(dim) - L) / lambda_max
        self.norm_adj = norm_adj
        
    def get_cell_position(self, k, cell_pos):
        """
        应用k次滤波器迭代获取新位置
        
        Args:
            k: 迭代次数
            cell_pos: 初始位置 (n, 2) array 或 list of tuples
            
        Returns:
            filtered_pos: 滤波后的位置
        """
        norm_adj = self.norm_adj
        
        # 转换输入格式
        if isinstance(cell_pos, list):
            cell_pos = np.array(cell_pos)
        
        # 迭代应用滤波器
        for _ in range(k):
            cell_pos = norm_adj @ cell_pos
            
        return cell_pos


# =============================================================================
# 第二部分: 工具函数
# =============================================================================

def make_dir(path):
    """创建目录"""
    if not os.path.isdir(path):
        os.makedirs(path)

def placement_region(fixed_pos):
    """从固定点位置计算布局区域"""
    if len(fixed_pos) == 0:
        return 0, 0, 100, 100
    xf = fixed_pos[:, 0]
    yf = fixed_pos[:, 1]
    return np.min(xf), np.min(yf), np.max(xf), np.max(yf)

def generate_initial_locations(fixed_cell_location, movable_num, scale, region=None, seed=None):
    """
    生成可移动节点的初始位置
    
    Args:
        fixed_cell_location: 固定节点位置
        movable_num: 可移动节点数量
        scale: 分布范围比例
        region: 布局区域 (x_min, y_min, x_max, y_max)
        seed: 随机种子
    """
    if region is None:
        x_min, y_min, x_max, y_max = placement_region(fixed_cell_location)
    else:
        x_min, y_min, x_max, y_max = region
        
    if seed is not None:
        np.random.seed(seed)
        
    random_initial = np.random.rand(int(movable_num), 2)
    random_initial[:, 1] += (random_initial[:, 0] == random_initial[:, 1]) * 0.01
    
    xcenter = (x_max - x_min) / 2 + x_min
    ycenter = (y_max - y_min) / 2 + y_min
    random_initial[:, 0] = ((random_initial[:, 0] - 0.5) * (x_max - x_min) * scale) + xcenter
    random_initial[:, 1] = ((random_initial[:, 1] - 0.5) * (y_max - y_min) * scale) + ycenter
    
    return random_initial


# =============================================================================
# 第三部分: GIFT接口 (使用真正的GIFT算法)
# =============================================================================

class GIFTInterface:
    """
    GIFT布局接口 - 使用真正的GIFT算法
    """
    
    def __init__(self, adj_matrix, fixed_positions=None, movable_num=None):
        """
        初始化GIFT接口
        
        Args:
            adj_matrix: 邻接矩阵 (sparse)
            fixed_positions: 固定节点位置 (n_fixed, 2)
            movable_num: 可移动节点数量
        """
        self.adj_matrix = adj_matrix
        self.n = adj_matrix.shape[0]
        
        if fixed_positions is not None and len(fixed_positions) > 0:
            self.fixed_positions = np.array(fixed_positions)
            self.movable_num = movable_num if movable_num else self.n - len(fixed_positions)
        else:
            self.fixed_positions = np.array([]).reshape(0, 2)
            self.movable_num = self.n
        self._init_location = None  # 添加这个变量用于保存初始位置
            
    def run_gift_layout(self, placement_region=None, scale=0.5, 
                        use_mixed_filter=True, seed=42):
        """
        运行GIFT布局算法
        
        Args:
            placement_region: 布局区域 (x_min, y_min, x_max, y_max)
            scale: 初始位置分布范围
            use_mixed_filter: 是否使用混合频率滤波器
            seed: 随机种子
            
        Returns:
            positions: 所有节点的最终位置 (n, 2)
        """
        print(f"  Running GIFT layout on {self.n} nodes...")
        
        # 设置布局区域
        if placement_region is None:
            if len(self.fixed_positions) > 0:
                x_min, y_min, x_max, y_max = placement_region_from_fixed(self.fixed_positions)
            else:
                x_min, y_min, x_max, y_max = 0, 0, 100, 100
        else:
            x_min, y_min, x_max, y_max = placement_region
            
        # 生成可移动节点的初始位置
        movable_init = generate_initial_locations(
            self.fixed_positions, 
            self.movable_num, 
            scale,
            region=(x_min, y_min, x_max, y_max),
            seed=seed
        )
        
        # 组合初始位置: [movable, fixed]
        if len(self.fixed_positions) > 0:
            init_location = np.vstack([movable_init, self.fixed_positions])
        else:
            init_location = movable_init
        
        # 保存初始位置
        self._init_location = init_location  # 保存初始位置
            
        # 将坐标平移到原点 (GIFT的标准做法)
        init_location_shifted = init_location.copy()
        init_location_shifted[:, 0] -= x_min
        init_location_shifted[:, 1] -= y_min
        
        start_time = time.time()
        
        if use_mixed_filter:
            # 使用混合频率滤波器 (原始GIFT方法)
            positions = self._run_mixed_filter(init_location_shifted)
        else:
            # 使用新滤波器
            positions = self._run_new_filter(init_location_shifted)
            
        end_time = time.time()
        print(f"  GIFT completed in {end_time - start_time:.3f}s")
        
        # 恢复固定节点位置
        if len(self.fixed_positions) > 0:
            positions = np.vstack([
                positions[:self.movable_num],
                self.fixed_positions - np.array([x_min, y_min])
            ])
            
        # 平移回原坐标系
        positions[:, 0] += x_min
        positions[:, 1] += y_min
        
        return positions
    
    def _run_mixed_filter(self, init_location):
        """
        运行混合频率滤波器 (原始GIFT方法)

        - Low-pass: σ=4, k=4
        - Mid-pass: σ=4, k=2
        - High-pass: σ=2, k=2
        - Final: 0.2*low + 0.7*mid + 0.1*high
        """
        gift = GiFt(self.adj_matrix)

        # Low-pass and Mid-pass share sigma=4, only train once
        gift.train(sigma=4)
        location_low = gift.get_cell_position(k=4, cell_pos=init_location.copy())
        location_mid = gift.get_cell_position(k=2, cell_pos=init_location.copy())

        # High-pass filter (different sigma)
        gift.train(sigma=2)
        location_high = gift.get_cell_position(k=2, cell_pos=init_location.copy())

        # 混合
        positions = 0.2 * location_low + 0.7 * location_mid + 0.1 * location_high

        return positions
    
    def _run_new_filter(self, init_location):
        """
        运行新滤波器 (基于拉普拉斯)
        """
        gift = GiFt(self.adj_matrix)
        gift.new_filter_train()
        positions = gift.get_cell_position(k=4, cell_pos=init_location.copy())
        return positions
    
    def get_xy_features(self, positions):
        """提取x/y坐标作为特征向量"""
        return positions[:, 0].copy(), positions[:, 1].copy()


def placement_region_from_fixed(fixed_pos):
    """从固定点位置计算布局区域"""
    if len(fixed_pos) == 0:
        return 0, 0, 100, 100
    return (np.min(fixed_pos[:, 0]), np.min(fixed_pos[:, 1]),
            np.max(fixed_pos[:, 0]), np.max(fixed_pos[:, 1]))


def _run_gift_for_cluster(args):
    """Worker function for parallel GIFT layout computation.

    Each invocation is independent and sets its own random seed,
    so results are deterministic and identical to the sequential version.
    """
    cid, sub_adj, region, scale, use_mixed, seed = args
    gift = GIFTInterface(sub_adj)
    print(f"[DEBUG] GIFT random_seed = {seed}")
    try:
        pos = gift.run_gift_layout(
            placement_region=region,
            scale=scale,
            use_mixed_filter=use_mixed,
            seed=seed,
        )
        x_feat, y_feat = gift.get_xy_features(pos)
        return (cid, pos, x_feat, y_feat)
    except Exception as e:
        print(f"[GIFT][warn] cluster={cid} failed: {e}")
        return (cid, None, None, None)


# =============================================================================
# 第四部分: FPGA文件解析器
# =============================================================================

class FPGABookshelfParser:
    """解析FPGA综合后的文件"""
    
    def __init__(self, benchmark_dir):
        self.benchmark_dir = benchmark_dir
        self.nodes = {}
        self.nets = {}
        self.placements = {}
        self.sites = {}
        self.sitemap = []
        self.lib_cells = {}
        self.resources = {}
        
        self.node_name_to_idx = {}
        self.idx_to_node_name = {}
        self.num_nodes = 0
        self.num_nets = 0
        self.chip_width = 0
        self.chip_height = 0
        self.macros = []                  # [node_name, ...]
        self.cascade_shape_groups = []    # [[node_name,...], [node_name,...], ...]

    def parse_aux(self, aux_file):
        """解析.aux文件"""
        
        files = {}
        if not aux_file:
            return files
        filepath = os.path.join(self.benchmark_dir, aux_file)
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        file_list = parts[1].strip().split()
                        for file_name in file_list:
                            ext = os.path.splitext(file_name)[1]
                            files[ext] = file_name
        return files
    
    def parse_nodes(self, nodes_file):
        """解析.nodes文件"""
        filepath = os.path.join(self.benchmark_dir, nodes_file)
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    node_name = parts[0]
                    cell_type = parts[1]
                    self.nodes[node_name] = {
                        'cell_type': cell_type,
                        'is_io': cell_type in ['IBUF', 'OBUF', 'BUFGCE', 'IOA', 'IOB', 'GCLK', 'IPPIN'],
                        'is_bram': cell_type in ['RAMB36E2', 'RAMA', 'RAMB'],
                        'is_dsp': cell_type in ['DSP48E2', 'DSP'],
                        'is_ff': cell_type in ['FDRE', 'SEQ'],
                        'is_lut': cell_type.startswith('LUT'),
                        'is_carry': cell_type in ['CARRY8', 'CARRY4']
                    }
        
        for idx, name in enumerate(self.nodes.keys()):
            self.node_name_to_idx[name] = idx
            self.idx_to_node_name[idx] = name
        
        self.num_nodes = len(self.nodes)
        print(f"Parsed {self.num_nodes} nodes")
        
        type_counts = defaultdict(int)
        for info in self.nodes.values():
            type_counts[info['cell_type']] += 1
        print(f"  Cell types: {dict(type_counts)}")
        
    def parse_nets(self, nets_file):
        """解析.nets文件"""
        filepath = os.path.join(self.benchmark_dir, nets_file)
        current_net = None
        current_pins = []
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if line.startswith('net '):
                    parts = line.split()
                    current_net = parts[1]
                    current_pins = []
                elif line == 'endnet':
                    if current_net and current_pins:
                        self.nets[current_net] = current_pins
                    current_net = None
                    current_pins = []
                elif current_net is not None:
                    parts = line.split()
                    if len(parts) >= 2:
                        current_pins.append({
                            'node': parts[0],
                            'pin': parts[1]
                        })
        
        self.num_nets = len(self.nets)
        print(f"Parsed {self.num_nets} nets")
        
    def parse_pl(self, pl_file):
        """解析.pl文件"""
        filepath = os.path.join(self.benchmark_dir, pl_file)
        if not os.path.exists(filepath):
            return
            
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    node_name = parts[0]
                    x = float(parts[1])
                    y = float(parts[2])
                    fixed = 'FIXED' in line.upper()
                    self.placements[node_name] = {'x': x, 'y': y, 'fixed': fixed}
        
        print(f"Parsed {len(self.placements)} placements")
        
    def parse_scl(self, scl_file):
        """解析.scl文件"""
        filepath = os.path.join(self.benchmark_dir, scl_file)
        current_section = None
        current_site = None
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if line.startswith('SITE '):
                    current_section = 'SITE'
                    current_site = line.split()[1]
                    self.sites[current_site] = {}
                elif line == 'END SITE':
                    current_section = None
                    current_site = None
                elif current_section == 'SITE' and current_site:
                    parts = line.split()
                    if len(parts) >= 2:
                        self.sites[current_site][parts[0]] = int(parts[1])
                elif line == 'RESOURCES':
                    current_section = 'RESOURCES'
                elif line == 'END RESOURCES':
                    current_section = None
                elif current_section == 'RESOURCES':
                    parts = line.split()
                    if len(parts) >= 2:
                        self.resources[parts[0]] = parts[1:]
                elif line.startswith('SITEMAP '):
                    current_section = 'SITEMAP'
                    parts = line.split()
                    self.chip_width = int(parts[1])
                    self.chip_height = int(parts[2])
                elif line == 'END SITEMAP':
                    current_section = None
                elif current_section == 'SITEMAP':
                    parts = line.split()
                    if len(parts) >= 3:
                        self.sitemap.append((int(parts[0]), int(parts[1]), parts[2]))
        
        print(f"Parsed FPGA architecture: {self.chip_width}x{self.chip_height}")
        
    def parse_lib(self, lib_file):
        """解析.lib文件"""
        filepath = os.path.join(self.benchmark_dir, lib_file)
        current_cell = None
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if line.startswith('CELL '):
                    current_cell = line.split()[1]
                    self.lib_cells[current_cell] = {'pins': []}
                elif line == 'END CELL':
                    current_cell = None
                elif current_cell and line.startswith('PIN '):
                    parts = line.split()
                    pin_info = {'name': parts[1], 'direction': parts[2] if len(parts) > 2 else 'UNKNOWN'}
                    if 'CLOCK' in line:
                        pin_info['is_clock'] = True
                    self.lib_cells[current_cell]['pins'].append(pin_info)
        
        print(f"Parsed {len(self.lib_cells)} library cells")

    def parse_macros(self, macros_file):
        """解析.macros文件：记录macro实例名集合（默认取每行第一列作为实例名）"""
        filepath = os.path.join(self.benchmark_dir, macros_file)
        if not os.path.exists(filepath):
            print(f"Warning: macros file not found: {filepath}")
            return

        macros = []
        seen = set()
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 兼容：一行可能不止一个字段，但macro实例名通常在第一列
                name = line.split()[0]
                if name not in seen:
                    seen.add(name)
                    macros.append(name)

        macros.sort()  # 确保跨运行的确定性顺序
        self.macros = macros
        print(f"Parsed {len(self.macros)} macros")
    def parse_cascade_shape_instances(self, instance_file):
        """
        解析 instance 文件中的 cascade locked cluster 信息：
        - 每行第一个 token 视为 node/instance 名
        - 空行或注释行分隔不同 group
        写入 self.cascade_shape_groups = [[node_name,...], ...]
        """
        filepath = os.path.join(self.benchmark_dir, instance_file)
        if not os.path.exists(filepath):
            print(f"Warning: instance file not found: {filepath}")
            return

        groups = []
        cur = []

        with open(filepath, 'r') as f:
            for raw in f:
                line = raw.strip()
                if (not line) or line.startswith('#'):
                    if cur:
                        groups.append(cur)
                        cur = []
                    continue
                cur.append(line.split()[0])

        if cur:
            groups.append(cur)

        self.cascade_shape_groups = groups
        print(f"Parsed {len(self.cascade_shape_groups)} cascade groups from instance: {instance_file}")
    def parse_cascade_shape(self, cascade_shape_file):
        """
        兼容两种格式：
        A) Shape <name> <w> <h> + BEGIN ... End  （你现有的 shapes 格式）
        B) 节点名列表（行首 token），空行分组 => cascade_shape_groups（用于锁簇）
        """
        filepath = os.path.join(self.benchmark_dir, cascade_shape_file)
        if not os.path.exists(filepath):
            print(f"Warning: cascade_shape file not found: {filepath}")
            return

        # 先扫一遍看是否包含 "Shape "
        has_shape_header = False
        with open(filepath, 'r') as f:
            for raw in f:
                s = raw.strip()
                if s.startswith('Shape '):
                    has_shape_header = True
                    break

        if not has_shape_header:
            # ---- B) 节点名分组模式：写入 cascade_shape_groups ----
            groups = []
            cur = []
            with open(filepath, 'r') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith('#'):
                        if cur:
                            groups.append(cur)
                            cur = []
                        continue
                    cur.append(line.split()[0])
            if cur:
                groups.append(cur)

            self.cascade_shape_groups = groups
            print(f"Parsed {len(self.cascade_shape_groups)} cascade groups")
            return

        # ---- A) Shape 模式：保留你原来的解析（写入 cascade_shapes）----
        shapes = {}
        current = None
        in_block = False

        with open(filepath, 'r') as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue

                if line.startswith('Shape '):
                    parts = line.split()
                    if len(parts) >= 4:
                        shape_name = parts[1]
                        try:
                            w = int(parts[2])
                            h = int(parts[3])
                        except ValueError:
                            current = None
                            in_block = False
                            continue
                        current = {'w': w, 'h': h, 'cells': []}
                        shapes[shape_name] = current
                        in_block = False
                    else:
                        current = None
                        in_block = False
                    continue

                if line == 'BEGIN':
                    in_block = True
                    continue

                if line.lower() in ('end', 'endshape'):
                    in_block = False
                    current = None
                    continue

                if in_block and current is not None:
                    cell_type = line.split()[0]
                    current['cells'].append(cell_type)

        self.cascade_shapes = shapes
        print(f"Parsed {len(self.cascade_shapes)} cascade shapes")


    def detect_macros_from_nodes(self, macro_cell_types=None):
        """
        从已解析的 .lib 和 .nodes 中自动识别 macro 实例。
        如果没有外部 .macros 文件，可以调用此方法作为 fallback。

        逻辑：在 .lib 中找到属于 macro 类型的 cell（如 DSP48E2、RAMB36E2 等），
        然后在 .nodes 中筛选出所有使用这些 cell type 的实例。

        Args:
            macro_cell_types: 用户指定的 macro cell type 集合。
                              如果为 None，则使用默认列表。
        """
        if macro_cell_types is None:
            # 默认将 BRAM 和 DSP 系列视为 macro
            macro_cell_types = {
                "RAMB36E2", "RAMB18E2", "RAMB36E1", "RAMB18E1",
                "DSP48E2", "DSP48E1",
                "RAMA", "RAMB", "DSP",
            }

        # 也可以从 .lib 推断：lib_cells 中定义的 cell type，
        # 如果在 macro_cell_types 集合中则视为 macro
        known_types = set(self.lib_cells.keys()) if self.lib_cells else set()
        active_macro_types = macro_cell_types & known_types if known_types else macro_cell_types

        macros = []
        seen = set()
        for node_name, info in self.nodes.items():
            ct = info.get("cell_type", "")
            if ct in active_macro_types or ct in macro_cell_types:
                if node_name not in seen:
                    seen.add(node_name)
                    macros.append(node_name)

        macros.sort()  # 确保确定性顺序
        self.macros = macros
        print(f"Auto-detected {len(self.macros)} macros from .nodes (types: {sorted(macro_cell_types & set(info['cell_type'] for info in self.nodes.values()))})")

    def build_cascade_shape_groups_from_nets(self,
                                            bram_cell_type="RAMB36E2",
                                            pin_keywords=("CASC", "CASCADE"),
                                            min_chain_len=2):
        """
        从 .nets 推断 BRAM cascade 实例链，写入 self.cascade_shape_groups = [[node_name,...], ...]
        依据：同一条 net 上存在 pin 名包含 CASC/CASCADE 的连接，且 node cell_type=RAMB36E2
        """
        from collections import defaultdict

        # 只在 nodes/nets 都已解析后调用
        if not self.nodes or not self.nets:
            return

        brams = {n for n, info in self.nodes.items() if info.get("cell_type") == bram_cell_type}
        if not brams:
            self.cascade_shape_groups = []
            return

        parent = {}
        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # 把 cascade net 上的 BRAM 连成连通分量（实例链）
        for net_name, pins in self.nets.items():
            has_casc = False
            bram_nodes = []
            for p in pins:
                pin = (p.get("pin") or "").upper()
                if any(k in pin for k in pin_keywords):
                    has_casc = True
                node = p.get("node")
                if node in brams:
                    bram_nodes.append(node)
            if not has_casc:
                continue
            bram_nodes = sorted(set(bram_nodes))
            if len(bram_nodes) < 2:
                continue
            base = bram_nodes[0]
            for other in bram_nodes[1:]:
                union(base, other)

        comps = defaultdict(list)
        for n in brams:
            if n in parent:
                comps[find(n)].append(n)

        groups = [sorted(v) for v in comps.values() if len(v) >= min_chain_len]
        self.cascade_shape_groups = groups
        print(f"Built {len(self.cascade_shape_groups)} cascade groups from nets (pins contain {pin_keywords})")


    def build_adjacency_matrix(self, ignore_clock_nets=True, weight_by_degree=True, max_fanout=500):
        """从nets构建邻接矩阵（等价但更快：COO 批量累积，避免 LIL 逐元素写入）"""
        n = len(self.nodes)
        if n == 0:
            return csc_matrix((0, 0))

        ignored_nets = 0
        processed_nets = 0

        # 分块累积，避免一次性 rows/cols/data 爆内存（不改变结果）
        FLUSH_EVERY = 3_000_000  # 经验值：大图可适当调大/调小
        rows, cols, data = [], [], []
        acc = None  # csr_matrix accumulator

        def flush():
            nonlocal rows, cols, data, acc
            if not rows:
                return
            m = coo_matrix((data, (rows, cols)), shape=(n, n), dtype=float).tocsr()
            # CSR/CSC 转换会自动合并重复项；这里显式 sum_duplicates 更稳妥
            m.sum_duplicates()
            acc = m if acc is None else (acc + m)
            rows, cols, data = [], [], []

        for net_name, pins in self.nets.items():
            node_indices = []
            has_clock_pin = False

            for pin_info in pins:
                node_name = pin_info['node']
                pin_name = pin_info['pin']

                if pin_name in ['C', 'CLK', 'CLKARDCLK', 'CLKBWRCLK']:
                    has_clock_pin = True

                if node_name in self.node_name_to_idx:
                    node_indices.append(self.node_name_to_idx[node_name])

            if ignore_clock_nets and has_clock_pin and len(node_indices) > 50:
                ignored_nets += 1
                continue
            if len(node_indices) > max_fanout:
                ignored_nets += 1
                continue
            if len(node_indices) < 2:
                continue

            processed_nets += 1
            k = len(node_indices)
            #weight = 2.0 / k if weight_by_degree else 1.0
            weight = 1/(k-1) if weight_by_degree else 1.0
            #修改clique graph 权重
            idx = np.asarray(node_indices, dtype=np.int32)

            # 对所有 i<j 的 pair 一次性生成（与原双重循环 + 对称写入完全等价）
            iu, ju = np.triu_indices(k, k=1)
            if iu.size == 0:
                continue

            # 上三角
            ri = idx[iu]
            ci = idx[ju]
            rows.extend(ri.tolist())
            cols.extend(ci.tolist())
            data.extend([weight] * iu.size)

            # 对称边
            rows.extend(ci.tolist())
            cols.extend(ri.tolist())
            data.extend([weight] * iu.size)

            if len(rows) >= FLUSH_EVERY:
                flush()

        flush()

        print(f"Processed {processed_nets} nets, ignored {ignored_nets}")
        if acc is None:
            return csc_matrix((n, n), dtype=float)
        return acc.tocsr()

    
    def get_placement_region(self):
        """获取布局区域"""
        return (0, 0, self.chip_width, self.chip_height)
    
    def get_io_node_indices(self):
        """获取IO节点索引"""
        io_indices = []
        for name, info in self.nodes.items():
            if info['is_io'] and name in self.node_name_to_idx:
                io_indices.append(self.node_name_to_idx[name])
        return io_indices


# =============================================================================
# 第五部分: Louvain Clustering
# =============================================================================

class LouvainClusterer:
    """使用Louvain算法进行聚类"""
    
    def __init__(self, adj_matrix, node_names=None):
        self.adj_matrix = adj_matrix
        self.n = adj_matrix.shape[0]
        self.node_names = node_names or [str(i) for i in range(self.n)]
        self.partition = None
        self.clusters = None
        
    def run_clustering(self, resolution=1.0, active_nodes=None, random_state=None):
        """
        Run Louvain clustering on (sub)graph.

        Returns:
            partition: dict[int,int]  # node_id -> cluster_id
        Side effects:
            self.partition, self.clusters
        """
        print(f"[DEBUG] random_state = {random_state}")
        import numpy as np
        from collections import defaultdict
        from sknetwork.clustering import Louvain as SparseLouvain

        # --- choose adjacency (full or induced subgraph) ---
        if active_nodes is not None:
            active_nodes = np.asarray(list(active_nodes), dtype=np.int64)
            sub_adj = self.adj_matrix[active_nodes, :][:, active_nodes].tocsr()
            # Louvain expects sparse matrix; ensure diagonal doesn't matter
            labels = SparseLouvain(resolution=resolution, random_state=random_state).fit_predict(sub_adj)
            partition = {int(active_nodes[i]): int(labels[i]) for i in range(len(active_nodes))}
        else:
            adj = self.adj_matrix.tocsr()
            labels = SparseLouvain(resolution=resolution, random_state=random_state).fit_predict(adj)
            partition = {int(i): int(labels[i]) for i in range(adj.shape[0])}

        # --- build clusters dict (cid -> [nodes]) ---
        clusters = defaultdict(list)
        for node, cid in partition.items():
            clusters[int(cid)].append(int(node))

        self.partition = partition
        self.clusters = dict(clusters)
        return partition
    
    def enforce_max_cluster_size(self, max_size, resolution=1.0, random_state=None):
        print(f"[DEBUG] enforce louvain random_state = {random_state}")
        if max_size is None:
            return
        max_size = int(max_size)

        # 收集所有 cluster，记录原始顺序中哪些需要拆分
        small_parts = []          # (original_order_index, [nodes])
        oversized_entries = []    # (original_order_index, sorted_nodes)
        for order_idx, nodes in enumerate(self.clusters.values()):
            ni = sorted(nodes)
            if len(ni) <= max_size:
                small_parts.append((order_idx, ni))
            else:
                oversized_entries.append((order_idx, ni))

        if not oversized_entries:
            return

        # ✅ 强制串行拆分，避免多进程浮点非确定性导致不可复现
        print(f"  [enforce_max] Splitting {len(oversized_entries)} oversized clusters sequentially (reproducibility mode)...")
        split_results = []
        for _, ni in oversized_entries:
            sub_adj = self.adj_matrix[ni, :][:, ni]
            local_parts = _split_recursive_local(sub_adj, max_size, resolution, random_state)
            split_results.append([[ni[i] for i in part] for part in local_parts])

        # 按原始顺序重建 cluster 列表，保持与原始串行版本一致的 ID 分配
        oversized_result_map = {oe[0]: sr for oe, sr in zip(oversized_entries, split_results)}
        all_parts = []
        for order_idx, nodes in enumerate(self.clusters.values()):
            if order_idx in oversized_result_map:
                all_parts.extend(oversized_result_map[order_idx])
            else:
                all_parts.append(sorted(nodes))

        # Rebuild clusters with consecutive IDs
        new_clusters = {i: part for i, part in enumerate(all_parts)}

        # safety: 如果因为任何原因仍存在超标簇，强制按 size 切块（保证 <= max_size）
        overs = [v for v in new_clusters.values() if len(v) > max_size]
        if overs:
            fixed = defaultdict(list)
            cid = 0
            for v in new_clusters.values():
                v = list(v)
                if len(v) <= max_size:
                    fixed[cid] = v
                    cid += 1
                else:
                    for i in range(0, len(v), max_size):
                        fixed[cid] = v[i:i+max_size]
                        cid += 1
            new_clusters = fixed

        self.clusters = dict(new_clusters)

    def get_large_clusters(self, min_size=10):
        """获取大型clusters"""
        if self.clusters is None:
            raise ValueError("Run clustering first")
        large = [(cid, nodes) for cid, nodes in self.clusters.items() if len(nodes) >= min_size]
        print(f"Found {len(large)} large clusters (size >= {min_size})")
        return large
    
    def get_cluster_subgraph(self, node_indices):
        """提取cluster子图"""
        node_indices = sorted(node_indices)
        old_to_new = {old: new for new, old in enumerate(node_indices)}
        new_to_old = {new: old for new, old in enumerate(node_indices)}
        sub_adj = self.adj_matrix[node_indices, :][:, node_indices]
        return sub_adj, old_to_new, new_to_old
    
    def export_partition(self, output_file):
        """导出partition结果"""
        with open(output_file, 'w') as f:
            for node_idx in range(self.n):
                cluster_id = self.partition.get(node_idx, -1)
                f.write(f"{cluster_id}\n")
        print(f"Partition exported to {output_file}")


def _split_recursive_local(sub_adj, max_size, resolution, random_state):
    """Recursively split a subgraph (local indices 0..N-1) until all parts <= max_size.

    Functionally equivalent to the original LouvainClusterer.enforce_max_cluster_size
    recursive logic, but operates on a local sub-adjacency matrix so it can be called
    in a worker process without needing the full adjacency matrix.
    """
    n = sub_adj.shape[0]
    if n <= max_size:
        return [list(range(n))]

    from sknetwork.clustering import Louvain as SparseLouvain
    labels = SparseLouvain(resolution=resolution, random_state=random_state).fit_predict(sub_adj.tocsr())

    parts_dict = defaultdict(list)
    for i, label in enumerate(labels):
        parts_dict[int(label)].append(i)
    parts = list(parts_dict.values())

    if len(parts) <= 1:
        mid = n // 2
        left = list(range(mid))
        right = list(range(mid, n))
        left_adj = sub_adj[left, :][:, left]
        right_adj = sub_adj[right, :][:, right]
        left_parts = _split_recursive_local(left_adj, max_size, resolution, random_state)
        right_parts = _split_recursive_local(right_adj, max_size, resolution, random_state)
        return left_parts + [[i + mid for i in p] for p in right_parts]

    result = []
    for part_local in parts:
        sub_sub = sub_adj[part_local, :][:, part_local]
        sub_parts = _split_recursive_local(sub_sub, max_size, resolution, random_state)
        for sp in sub_parts:
            result.append([part_local[i] for i in sp])
    return result


def _split_oversized_cluster(args):
    """Worker function for parallel cluster splitting.

    Takes a pre-extracted sub-adjacency matrix and global index list,
    splits recursively, and returns list of global-index node lists.
    """
    sub_adj, global_indices, max_size, resolution, random_state = args
    local_parts = _split_recursive_local(sub_adj, max_size, resolution, random_state)
    return [[global_indices[i] for i in part] for part in local_parts]


# =============================================================================
# 第六部分: SpecPart接口
# =============================================================================

class SpecPartInterface:
    """SpecPart输入生成器"""
    
    def __init__(self, num_vertices, hyperedges, x_features, y_features):
        self.num_vertices = num_vertices
        self.hyperedges = hyperedges
        self.x_features = x_features
        self.y_features = y_features
        
    def export_hypergraph_hmetis(self, output_file):
        """导出为hmetis格式"""
        with open(output_file, 'w') as f:
            f.write(f"{len(self.hyperedges)} {self.num_vertices}\n")
            for hedge in self.hyperedges:
                vertices = ' '.join(str(v + 1) for v in hedge)
                f.write(f"{vertices}\n")
        print(f"  Hypergraph exported to {output_file}")
        
    def export_features(self, output_prefix):
        """导出特征向量"""
        np.savetxt(f"{output_prefix}_x.txt", self.x_features, fmt='%.6f')
        np.savetxt(f"{output_prefix}_y.txt", self.y_features, fmt='%.6f')
        features = np.column_stack([self.x_features, self.y_features])
        np.savetxt(f"{output_prefix}_xy.txt", features, fmt='%.6f')
        print(f"  Features exported to {output_prefix}_*.txt")
        
    def generate_specpart_input(self, output_dir, design_name):
        """生成SpecPart输入文件"""
        os.makedirs(output_dir, exist_ok=True)
        
        hg_file = os.path.join(output_dir, f"{design_name}.hgr")
        self.export_hypergraph_hmetis(hg_file)
        
        feature_prefix = os.path.join(output_dir, design_name)
        self.export_features(feature_prefix)
        
        config = {
            'hypergraph_file': hg_file,
            'x_features': f"{feature_prefix}_x.txt",
            'y_features': f"{feature_prefix}_y.txt",
            'num_vertices': self.num_vertices,
            'num_hyperedges': len(self.hyperedges)
        }
        
        config_file = os.path.join(output_dir, f"{design_name}_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return config


# =============================================================================
# 第七部分: 完整Pipeline
# =============================================================================

class FPGAClusteringPipeline:
    """完整的FPGA聚类Pipeline"""
    

    def __init__(self, benchmark_dir, output_dir):
        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir
        self.parser = None
        self.clusterer = None
        self.cluster_layouts = {}
        
        os.makedirs(output_dir, exist_ok=True)
    def _build_node_to_nets(self, nets):
        # nets: {net_name: [{'node': name, 'pin': ...}, ...]}
        # 使用 list + seen-set 保证去重 + 确定性顺序（插入序 = nets 遍历序）
        node_to_nets = {}
        for net_name, pins in nets.items():
            for p in pins:
                n = p['node']
                if n not in node_to_nets:
                    node_to_nets[n] = []
                lst = node_to_nets[n]
                # 去重：只添加一次（同一 net 可能多次出现在同一 node 的不同 pin 上）
                if not lst or lst[-1] != net_name:
                    # 快速路径：大多数情况下最后一个元素就是重复项
                    if net_name not in lst:
                        lst.append(net_name)
        return node_to_nets

    def _build_locked_clusters(self, parser, macro_neighbor_depth=-1):
        """
        构建 locked clusters。

        Args:
            parser: FPGABookshelfParser 实例
            macro_neighbor_depth: macro 沿合法网线抓取邻居的层数。
                -1 = 不特殊处理 macro，不进行 lock，当作普通单元；
                0  = 仅将 macro 本身作为 locked cluster，不抓取邻居；
                1  = 抓取直接邻居（默认）；
                2  = 抓取邻居的邻居；依此类推。
        """
        # ✅ 你这份 parser 的正确 name<->idx 映射
        name2idx = dict(parser.node_name_to_idx)
        idx2name = dict(parser.idx_to_node_name)
        node_to_nets = self._build_node_to_nets(parser.nets)

        locked = []          # [{'lock_type': 'cascade'/'macro', 'node_indices':[...]}]
        used = set()         # 已被锁住的 global indices

        # 1) cascade_shape groups => locked clusters
        for grp in parser.cascade_shape_groups:
            idxs = []
            for nm in grp:
                if nm in name2idx:
                    idxs.append(name2idx[nm])
            idxs = sorted(set(idxs))
            if idxs:
                used.update(idxs)
                locked.append({"lock_type": "cascade", "node_indices": idxs})

        # 2) macros => macro + multi-layer connected nodes (same nets)
        macro_names = sorted(getattr(parser, "macros", []) or [])  # sorted 确保确定性
        macro_set = set(macro_names)

        # 过滤阈值：防止 macro 通过 clock/reset 等大扇出网吞掉全设计
        CLOCK_PIN_HINTS = {"C", "CLK", "CLKARDCLK", "CLKBWRCLK"}
        CLOCK_FANOUT_SKIP = 50          # 和你 build_adjacency_matrix 的策略一致
        MACRO_NET_FANOUT_LIMIT = 200    # 额外限制：任何 >200 pin 的网都不扩张

        def _get_neighbors_of_node(node_name, exclude_set):
            """获取一个节点沿合法网线连接的邻居 idx 集合（不含 macro、不含自身）"""
            neighbors = set()
            for net_name in node_to_nets.get(node_name, []):
                pins = parser.nets.get(net_name, [])
                if not pins:
                    continue

                # high-fanout net 直接跳过
                if len(pins) > MACRO_NET_FANOUT_LIMIT:
                    continue

                # clock-like net（含 clock pin 且扇出大）跳过
                has_clk_pin = False
                for p in pins:
                    pin = (p.get("pin") or "")
                    up = pin.upper()
                    if (pin in CLOCK_PIN_HINTS) or ("CLK" in up):
                        has_clk_pin = True
                        break
                if has_clk_pin and len(pins) > CLOCK_FANOUT_SKIP:
                    continue

                # 收集邻居：不吞其它 macro
                for p in pins:
                    nm = p.get("node")
                    if not nm or nm == node_name:
                        continue
                    if nm in macro_set:
                        continue
                    if nm in name2idx:
                        idx = name2idx[nm]
                        if idx not in exclude_set:
                            neighbors.add(idx)
            return neighbors

        depth = int(macro_neighbor_depth)

        # depth < 0 => 完全不处理 macro，当作普通单元
        if depth < 0:
            print(f"[locked] macro_neighbor_depth={depth}, skipping all macro locking")
            return locked, used

        for macro_nm in macro_names:
            if macro_nm not in name2idx:
                continue
            m = name2idx[macro_nm]

            # cascade > macro：macro 自己若已在 cascade 里，跳过
            if m in used:
                continue

            conn = {m}

            # depth == 0 => 仅 macro 本身作为 locked cluster，不抓取邻居
            # depth >= 1 => 逐层扩展邻居
            if depth >= 1:
                current_frontier_names = {macro_nm}  # 当前层的节点名
                for layer in range(depth):
                    next_frontier = set()
                    for frontier_nm in current_frontier_names:
                        neighbors = _get_neighbors_of_node(frontier_nm, conn)
                        next_frontier.update(neighbors)

                    if not next_frontier:
                        break

                    conn.update(next_frontier)
                    # 下一层的 frontier 是本层新加入的节点
                    current_frontier_names = set()
                    for idx in next_frontier:
                        if idx in idx2name:
                            current_frontier_names.add(idx2name[idx])

            # 去掉 cascade 已占用节点
            conn = sorted(set(conn) - used)
            if not conn:
                continue

            used.update(conn)
            locked.append({"lock_type": "macro", "node_indices": conn})

        return locked, used
    def _cluster_centroid_from_pl(self, node_indices):
        xs, ys = [], []
        for g in node_indices:
            nm = self.parser.idx_to_node_name[g]
            pl = self.parser.placements.get(nm)
            if pl is not None:
                xs.append(float(pl["x"]))
                ys.append(float(pl["y"]))
        if xs:
            return float(np.mean(xs)), float(np.mean(ys))
        # 没有任何 pl，就用芯片中心
        return float(self.parser.chip_width) * 0.5, float(self.parser.chip_height) * 0.5

    def _merge_small_louvain_clusters_into_large(
        self,
        clusters: dict[int, list[int]],
        min_cluster_size: int,
        max_cluster_size: int | None,
    ) -> dict[int, list[int]]:
        """
        把 <min_cluster_size 的 Louvain 簇，合并进“连接最强”的其它簇。
        连接强度：用 adj_matrix 边权累计。
        目标：进入 GIFT/SpecPart 之前不再有小簇。
        功能等价，但用 CSR 快速遍历邻居，避免 CSC.getrow() 的巨大开销。
        """
        if not clusters:
            return clusters

        import numpy as np
        from collections import defaultdict

        # 一次性转 CSR（只在这里转，不改变外部结构）
        adj = self.adj_matrix.tocsr()
        indptr, indices, data = adj.indptr, adj.indices, adj.data
        n_nodes = adj.shape[0]

        # 用数组做 node -> cid 映射，比 dict 快很多
        node2cid = np.full(n_nodes, -1, dtype=np.int64)
        for cid, ns in clusters.items():
            arr = np.asarray(ns, dtype=np.int64)
            # 保险：防越界
            arr = arr[(arr >= 0) & (arr < n_nodes)]
            node2cid[arr] = int(cid)

        # 只需要做一轮：合并只会让簇变大，不会产生“新的小簇”
        small = [cid for cid, ns in clusters.items() if len(ns) < min_cluster_size]
        small.sort(key=lambda c: len(clusters[c]))

        def pick_target(scid: int) -> int | None:
            sc_nodes = clusters.get(scid)
            if not sc_nodes:
                return None

            weights = defaultdict(float)

            # 累加 scid 到其它簇的连接权重
            for n in sc_nodes:
                n = int(n)
                if n < 0 or n >= n_nodes:
                    continue
                s, e = indptr[n], indptr[n + 1]
                for nb, w in zip(indices[s:e], data[s:e]):
                    tcid = int(node2cid[int(nb)])
                    if tcid == -1 or tcid == scid:
                        continue
                    weights[tcid] += float(w)

            # 没邻居：并到最大簇（尽量不超过 max）
            if not weights:
                others = [cid for cid in clusters.keys() if cid != scid]
                if not others:
                    return None
                
                if max_cluster_size is not None:
                    fit = [cid for cid in others if len(clusters[cid]) + len(sc_nodes) <= max_cluster_size]
                    if fit:
                        return max(fit, key=lambda c: len(clusters[c]))
                    else:
                        # ✅ [修复] 如果所有合并方案都会导致超限，则不合并，保持原样
                        return None
                
                # 如果没有 max_cluster_size 限制，才合并到最大的
                return max(others, key=lambda c: len(clusters[c]))

            # 有邻居：按 (weight, size) 选最优，若 max 限制不满足则选下一个
            cand = sorted(weights.items(), key=lambda kv: (kv[1], len(clusters.get(kv[0], []))), reverse=True)
            if max_cluster_size is not None:
                for tcid, _ in cand:
                    if tcid in clusters and len(clusters[tcid]) + len(sc_nodes) <= max_cluster_size:
                        return tcid
                # 所有候选合并后都会超过 max_cluster_size，不合并
                return None
            return cand[0][0]

        # 合并
        for idx_sc, scid in enumerate(small, start=1):
            if scid not in clusters:
                continue
            tgt = pick_target(scid)
            if tgt is None or tgt not in clusters or tgt == scid:
                continue

            sc_nodes = clusters[scid]
            clusters[tgt].extend(sc_nodes)

            arr = np.asarray(sc_nodes, dtype=np.int64)
            arr = arr[(arr >= 0) & (arr < n_nodes)]
            node2cid[arr] = int(tgt)

            del clusters[scid]

            # 可选：给你一个进度心跳，避免“以为卡死”
            if idx_sc % 500 == 0:
                print(f"[merge-small] merged {idx_sc}/{len(small)} small clusters...")

        return clusters


    def run_pipeline(self, aux_file, min_cluster_size=50, louvain_resolution=1.0,
                     gift_scale=0.5, use_mixed_filter=True, max_cluster_size=10000,
                     cluster_random_seed: int = 42, macro_neighbor_depth: int = -1,
                     max_fanout: int = 500, run_gift_layout: bool = True):
        # 设置全局随机种子，确保可复现性
        import random
        cluster_random_seed = int(cluster_random_seed)
        random.seed(cluster_random_seed)
        np.random.seed(cluster_random_seed)
        print(f"[Seed] fpga_clustering_pipeline_gift cluster_random_seed = {cluster_random_seed}")
        print("[DEBUG] max_cluster_size =", max_cluster_size)
        # ✅ 用本文件已有的解析入口（_parse_files 会内部创建 parser 并解析 nodes/nets/pl/scl/lib/macros/cascade）
        self._parse_files(aux_file)

        # ✅ 1) 先构建 locked clusters
        locked_clusters, used_nodes = self._build_locked_clusters(self.parser, macro_neighbor_depth=macro_neighbor_depth)

        if locked_clusters:
            locked_sizes = sorted([len(lc["node_indices"]) for lc in locked_clusters], reverse=True)
            print(f"[locked] num_locked_clusters = {len(locked_clusters)}, top_sizes = {locked_sizes[:10]}")
            if max_cluster_size is not None:
                big_locked = [i for i,s in enumerate(locked_sizes) if s > max_cluster_size]
                if big_locked:
                    print(f"[locked][warn] {len(big_locked)} locked clusters exceed max_cluster_size={max_cluster_size} (by design not split)")


        all_nodes = set(range(self.parser.num_nodes))

        # 2) build adjacency — must be built before computing degrees
        self.adj_matrix = self.parser.build_adjacency_matrix(max_fanout=max_fanout)

        # Store max_fanout for delayed_assign_isolated_nodes()
        self.max_fanout = max_fanout

        # Identify isolated nodes (degree=0 after high-fanout net filtering)
        degrees = np.array(self.adj_matrix.sum(axis=1)).flatten()
        candidate_active = all_nodes - used_nodes
        isolated_nodes = {v for v in candidate_active if degrees[v] == 0}
        active_nodes = sorted(candidate_active - isolated_nodes)

        # Store for delayed assignment after Phase 1 completes
        self.isolated_nodes = isolated_nodes

        print(f"[isolated] {len(isolated_nodes)} nodes have degree=0 in filtered adj, "
              f"deferred from Louvain")

        self.clusterer = LouvainClusterer(self.adj_matrix)
        partition = self.clusterer.run_clustering(
            resolution=louvain_resolution,
            active_nodes=active_nodes,
            #random_state=10000 #固定louvain种子进行实验 
            random_state=cluster_random_seed  # 由外部 cluster_random_seed 统一控制
        )

        # ------------------------------------------------------------
        #  Step 3: build self.clusterer.clusters from partition
        # ------------------------------------------------------------
        from collections import defaultdict
        base_clusters = defaultdict(list)
        for gidx, cid in partition.items():
            base_clusters[int(cid)].append(int(gidx))

        # 写入 clusterer.clusters，供 enforce_max_cluster_size 使用
        self.clusterer.clusters = {cid: nodes for cid, nodes in base_clusters.items()}
        pre_max = max((len(v) for v in self.clusterer.clusters.values()), default=0)
        print(f"[louvain] pre-enforce num_clusters={len(self.clusterer.clusters)}, max_size={pre_max}")

        # ✅ DEBUG: 可复现性指纹 - Louvain 初始分区
        import hashlib as _hl
        _cluster_sizes = sorted([len(v) for v in self.clusterer.clusters.values()], reverse=True)
        _fp = _hl.md5(str(_cluster_sizes).encode()).hexdigest()[:12]
        print(f"[DEBUG][Reproducibility] Louvain initial: fingerprint={_fp}, "
              f"top5_sizes={_cluster_sizes[:5]}, total_nodes={sum(_cluster_sizes)}")

        # ------------------------------------------------------------
        #  Step 4: enforce max_cluster_size by recursive Louvain
        # 说明：这里会把 self.clusterer.clusters 改写成满足 max_size 的新 clusters
        # ------------------------------------------------------------
        if max_cluster_size is not None:
            #  真正执行切分
            self.clusterer.enforce_max_cluster_size(
                max_size=max_cluster_size,
                resolution=louvain_resolution,
                #random_state=10000,#固定louvain randoms_eed
                random_state=cluster_random_seed,#传入random_seed
            )

        post_max = max((len(v) for v in self.clusterer.clusters.values()), default=0)
        print(f"[louvain] post-enforce num_clusters={len(self.clusterer.clusters)}, max_size={post_max}")

        # ✅ DEBUG: 可复现性指纹 - enforce 后
        _sizes_post = sorted([len(v) for v in self.clusterer.clusters.values()], reverse=True)
        _fp_post = _hl.md5(str(_sizes_post).encode()).hexdigest()[:12]
        print(f"[DEBUG][Reproducibility] Post-enforce: fingerprint={_fp_post}, "
              f"num_clusters={len(self.clusterer.clusters)}, top5_sizes={_sizes_post[:5]}")

        if max_cluster_size is not None and post_max > max_cluster_size:
            raise RuntimeError(
                f"enforce_max_cluster_size failed: post_max={post_max} > max_cluster_size={max_cluster_size}. "
                "This usually means enforce_max_cluster_size didn't run as expected."
            )

        louvain_clusters = self.clusterer.clusters

        # ============================================================
        # NEW: merge small Louvain clusters into nearby large clusters
        # 目的：避免很多 size 很小的 cluster 进入 SpecPart 产生大量 size=1 sub-cluster
        # ============================================================
        print("[merge-small] start")
        louvain_clusters = self._merge_small_louvain_clusters_into_large(
            louvain_clusters,
            min_cluster_size=min_cluster_size,
            max_cluster_size=max_cluster_size,
        )
        print("[merge-small] done")
        # 合并可能把大簇又推超过 max，再 enforce 一次
        self.clusterer.clusters = louvain_clusters
        if max_cluster_size is not None:
            self.clusterer.enforce_max_cluster_size(
                max_size=max_cluster_size,
                resolution=louvain_resolution,
                #random_state=10000#固定enforce种子进行实验
                random_state=cluster_random_seed,
            )

        # enforce 之后可能又出现小簇（极少数），再 merge 一次兜底
        louvain_clusters = self._merge_small_louvain_clusters_into_large(
            self.clusterer.clusters,
            min_cluster_size=min_cluster_size,
            max_cluster_size=max_cluster_size,
        )
        self.clusterer.clusters = louvain_clusters

        # ✅ DEBUG: 可复现性指纹 - 最终 cluster 分配
        _final_sizes = sorted([len(v) for v in louvain_clusters.values()], reverse=True)
        _fp2 = _hl.md5(str(_final_sizes).encode()).hexdigest()[:12]
        print(f"[DEBUG][Reproducibility] Final clusters: fingerprint={_fp2}, "
              f"num_clusters={len(louvain_clusters)}, top5_sizes={_final_sizes[:5]}, "
              f"total_nodes={sum(_final_sizes)}")

        # 4) 组装 cluster_layouts：先 Louvain，再追加 locked（cascade > macro 的顺序已经在 _build_locked_clusters 里保证）
        cluster_layouts = {}
        clustering_results = {}

        # 给每个 cluster 一个“默认 positions”（没跑 GIFT 的就用原 pl/随机）
        def default_positions(node_indices):
            pos = []
            for g in node_indices:
                nm = self.parser.idx_to_node_name[g]  # ✅ idx -> name
                if nm in self.parser.placements:
                    x = self.parser.placements[nm]['x']
                    y = self.parser.placements[nm]['y']
                    pos.append([float(x), float(y)])
                else:
                    pos.append([0.0, 0.0])
            return np.array(pos, dtype=float)

        # 4.1 Louvain clusters（全量都放进 cluster_layouts；是否跑 GIFT 由大小控制）
        next_cluster_id = 0
        # 保证 Louvain cluster_id 连续（0..K-1）
        cid_map = {old: i for i, old in enumerate(sorted(louvain_clusters.keys()))}
        for old_cid, nodes in louvain_clusters.items():
            cid = cid_map[old_cid]
            nodes = sorted(nodes)

            pos0 = default_positions(nodes)  # (n,2)

            cluster_layouts[cid] = {
                "node_indices": nodes,
                "positions": pos0,
                "x_features": pos0[:, 0].copy(),
                "y_features": pos0[:, 1].copy(),
                "locked": False,
            }

            next_cluster_id = max(next_cluster_id, cid + 1)

        # 4.2 locked clusters：追加到 cluster_layouts；并提前注入 clustering_results（单 subcluster）
        for lc in locked_clusters:
            cid = next_cluster_id
            next_cluster_id += 1

            nodes = lc["node_indices"]
            pos0 = default_positions(nodes)

            cluster_layouts[cid] = {
                "node_indices": nodes,
                "positions": pos0,
                "x_features": pos0[:, 0].copy(),
                "y_features": pos0[:, 1].copy(),
                "locked": True,
                "lock_type": lc["lock_type"],   # 'cascade' or 'macro'
            }

            clustering_results[cid] = {
                "clusters": [list(range(len(nodes)))],
                "num_sub_clusters": 1,
                "locked": True,
                "lock_type": lc["lock_type"],
            }

        # 5) 只对满足阈值的 cluster 跑 GIFT（其余保持默认 positions）
        # ✅ DEBUG: 打印 cluster_layouts 指纹
        _cl_sizes = [len(cluster_layouts[k]["node_indices"]) for k in sorted(cluster_layouts.keys())]
        _cl_fp = _hl.md5(str(_cl_sizes).encode()).hexdigest()[:12]
        print(f"[DEBUG][Reproducibility] cluster_layouts: fingerprint={_cl_fp}, "
              f"num_clusters={len(cluster_layouts)}, sizes_sorted_top5={sorted(_cl_sizes, reverse=True)[:5]}")

        if run_gift_layout:
            # Collect GIFT tasks for parallel execution
            region = self.parser.get_placement_region()
            gift_tasks = []
            for cid, info in cluster_layouts.items():
                nodes = info["node_indices"]
                if info.get("locked", False):
                    continue
                if len(nodes) < min_cluster_size or (max_cluster_size is not None and len(nodes) > max_cluster_size):
                    continue
                sub_adj = self.adj_matrix[nodes, :][:, nodes]
                # ✅ 固定 GIFT seed = cluster_random_seed，不再加 cid 偏移
                # 这样无论 Louvain 分配的 cid 如何变化，每个 cluster 的 GIFT 布局种子都一致
                gift_tasks.append((cid, sub_adj, region, gift_scale, use_mixed_filter,
                                   cluster_random_seed))
            if gift_tasks:
                # ✅ 强制串行执行 GIFT，避免多进程导致不可复现
                print(f"  [GIFT] Running on {len(gift_tasks)} clusters sequentially (reproducibility mode)...")
                gift_results = [_run_gift_for_cluster(t) for t in gift_tasks]

                for cid, gift_pos, x_feat, y_feat in gift_results:
                    if gift_pos is not None:
                        cluster_layouts[cid]["positions"] = gift_pos
                        cluster_layouts[cid]["x_features"] = x_feat
                        cluster_layouts[cid]["y_features"] = y_feat
                    else:
                        print(f"[GIFT][warn] cluster={cid} failed, keeping default positions.")
        else:
            print("  [GIFT] Skipped. Using Louvain/default positions directly.")
        #  暴露给 EnhancedFPGAPipeline / cluster placement
        self.clustering_results = clustering_results
        return cluster_layouts

    def delayed_assign_isolated_nodes(self, cluster_layouts, clustering_results):
        """
        Post-Phase-1 delayed assignment: absorb isolated nodes (degree=0 in
        filtered adjacency) into existing clusters using high-fanout net scoring.

        For each unassigned node v, only examines nets with fanout >= FANOUT_THRESHOLD
        (the same nets excluded from the adjacency matrix). Scores each candidate
        cluster by sum of 1/fanout(e) over high-fanout nets connecting v to that cluster.
        """
        if not hasattr(self, 'isolated_nodes') or not self.isolated_nodes:
            return cluster_layouts, clustering_results

        FANOUT_THRESHOLD = getattr(self, 'max_fanout', 500)  # matches build_adjacency_matrix()

        isolated = self.isolated_nodes
        print(f"[delayed-assign] Absorbing {len(isolated)} isolated nodes ...")

        # 1) Build node -> cluster_id mapping from final cluster_layouts
        node2cid = {}
        for cid, info in cluster_layouts.items():
            for n in info['node_indices']:
                node2cid[n] = cid

        # 2) Pre-build index: for isolated nodes, collect only high-fanout nets
        #    node_idx -> list of (fanout, [node_indices_in_net])
        node_to_hf_nets = defaultdict(list)
        for net_name, pins in self.parser.nets.items():
            pin_indices = []
            for pin_info in pins:
                pn = pin_info['node']
                if pn in self.parser.node_name_to_idx:
                    pin_indices.append(self.parser.node_name_to_idx[pn])
            if len(pin_indices) < FANOUT_THRESHOLD:
                continue  # skip low-fanout nets — already handled by adjacency matrix
            for idx in pin_indices:
                if idx in isolated:
                    node_to_hf_nets[idx].append((len(pin_indices), pin_indices))

        # 3) Score and assign each isolated node
        assigned_count = 0
        fallback_count = 0
        for v in sorted(isolated):
            scores = defaultdict(float)
            for k, pin_indices in node_to_hf_nets.get(v, []):
                alpha = 1.0 / k
                seen_clusters = set()
                for u in pin_indices:
                    if u == v:
                        continue
                    c = node2cid.get(u)
                    if c is not None and c not in seen_clusters:
                        scores[c] += alpha
                        seen_clusters.add(c)

            if scores:
                best_cid = max(scores, key=scores.get)
                assigned_count += 1
            else:
                # No high-fanout net connects to any clustered node — fallback to largest
                best_cid = max(cluster_layouts,
                               key=lambda c: len(cluster_layouts[c]['node_indices']))
                fallback_count += 1

            # Append to cluster_layouts
            cluster_layouts[best_cid]['node_indices'].append(v)
            # Append a default position for the new node
            nm = self.parser.idx_to_node_name.get(v)
            if nm and nm in self.parser.placements:
                x = float(self.parser.placements[nm]['x'])
                y = float(self.parser.placements[nm]['y'])
            else:
                x, y = 0.0, 0.0
            pos = cluster_layouts[best_cid]['positions']
            if isinstance(pos, np.ndarray):
                cluster_layouts[best_cid]['positions'] = np.vstack([pos, [x, y]])
            else:
                pos.append([x, y])

            # Append to clustering_results — add to first sub-cluster
            if best_cid in clustering_results:
                cr = clustering_results[best_cid]
                local_idx = len(cluster_layouts[best_cid]['node_indices']) - 1
                if cr.get('clusters') and len(cr['clusters']) > 0:
                    cr['clusters'][0].append(local_idx)

            node2cid[v] = best_cid

        print(f"[delayed-assign] done: {assigned_count} by high-fanout net score, "
              f"{fallback_count} fallback to largest cluster")

        return cluster_layouts, clustering_results

    def _parse_files(self, aux_file):
        """解析所有文件"""
        self.parser = FPGABookshelfParser(self.benchmark_dir)
        files = self.parser.parse_aux(aux_file)

        if aux_file:
            files = self.parser.parse_aux(aux_file)
        else:
            files = {}
            for f in os.listdir(self.benchmark_dir):
                ext = os.path.splitext(f)[1]
                if ext in ['.nodes', '.nets', '.pl', '.scl', '.lib', '.macros', '.cascade_shape','.cascade_shape_instances','.instance']:
                    files[ext] = f
        
        print(f"  Found files: {files}")
        
        if '.nodes' in files:
            self.parser.parse_nodes(files['.nodes'])
        if '.nets' in files:
            self.parser.parse_nets(files['.nets'])
        if '.pl' in files:
            self.parser.parse_pl(files['.pl'])
        if '.scl' in files:
            self.parser.parse_scl(files['.scl'])
        if '.lib' in files:
            self.parser.parse_lib(files['.lib'])
        if '.macros' in files:
            self.parser.parse_macros(files['.macros'])
        else:
            # 没有外部 .macros 文件时，从 .nodes + .lib 自动识别 macro 实例
            if self.parser.nodes:
                print("[auto-detect] No .macros file found, detecting macros from .nodes/.lib ...")
                self.parser.detect_macros_from_nodes()
        if '.cascade_shape_instances' in files:
            self.parser.parse_cascade_shape_instances(files['.cascade_shape_instances'])
        elif '.instance' in files:
            self.parser.parse_cascade_shape_instances(files['.instance'])

        if '.cascade_shape' in files:
            self.parser.parse_cascade_shape(files['.cascade_shape'])
            # 如果 cascade_shape 是 Shape 模板格式（A），默认不会产生 groups
            # 则从 nets 推断实例链分组（BRAM cascade chains）
            '''
            if not getattr(self.parser, "cascade_shape_groups", None):
                self.parser.build_cascade_shape_groups_from_nets()
            elif len(self.parser.cascade_shape_groups) == 0:
                self.parser.build_cascade_shape_groups_from_nets()
            '''
        else:
            # 没有外部 cascade 文件时，尝试从 .nets 推断 BRAM cascade chains
            has_cascade_instances = '.cascade_shape_instances' in files or '.instance' in files
            if not has_cascade_instances and self.parser.nodes and self.parser.nets:
                if not getattr(self.parser, "cascade_shape_groups", None) or len(self.parser.cascade_shape_groups) == 0:
                    print("[auto-detect] No .cascade_shape file found, inferring cascade groups from .nets ...")
                    self.parser.build_cascade_shape_groups_from_nets()

    def _generate_specpart_inputs(self):
        """为每个cluster生成SpecPart输入"""
        for cluster_id, layout_info in self.cluster_layouts.items():
            node_indices = layout_info['node_indices']
            x_features = layout_info['x_features']
            y_features = layout_info['y_features']
            
            hyperedges = self._extract_cluster_hyperedges(node_indices)
            
            if len(hyperedges) == 0:
                print(f"  Cluster {cluster_id}: No internal nets, skipping")
                continue
            
            specpart = SpecPartInterface(
                num_vertices=len(node_indices),
                hyperedges=hyperedges,
                x_features=x_features,
                y_features=y_features
            )
            
            cluster_dir = os.path.join(self.output_dir, f"cluster_{cluster_id}")
            specpart.generate_specpart_input(cluster_dir, f"cluster_{cluster_id}")
    
    def _extract_cluster_hyperedges(self, node_indices):
        """提取cluster内部的超边（等价但更快：只遍历cluster涉及到的nets）"""
        node_set = set(node_indices)
        old_to_new = {old: new for new, old in enumerate(node_indices)}

        # ---- lazy cache: global_idx -> list of net_name (允许重复，功能等价) ----
        if not hasattr(self, "_node_to_nets_idx"):
            # 这里用 list-of-lists，避免 set 的巨大内存开销
            n_nodes = len(self.parser.nodes)
            node_to_nets_idx = [[] for _ in range(n_nodes)]

            # 记录 net 的原始遍历顺序，用于稳定输出顺序
            net_order = {}
            for ord_i, (net_name, pins) in enumerate(self.parser.nets.items()):
                net_order[net_name] = ord_i
                for pin in pins:
                    node_name = pin.get("node")
                    if node_name in self.parser.node_name_to_idx:
                        gi = self.parser.node_name_to_idx[node_name]
                        if 0 <= gi < n_nodes:
                            node_to_nets_idx[gi].append(net_name)

            self._node_to_nets_idx = node_to_nets_idx
            self._net_order = net_order

        node_to_nets_idx = self._node_to_nets_idx
        net_order = self._net_order

        # ---- candidate nets: 只取 cluster 内节点触达的 nets ----
        candidate_nets = set()
        for gi in node_indices:
            if 0 <= gi < len(node_to_nets_idx):
                candidate_nets.update(node_to_nets_idx[gi])
        # ---- 过滤大扇出和 clock-like nets ----
        filtered_nets = set()
        for net_name in candidate_nets:
            pins = self.parser.nets.get(net_name, [])
            if not pins:
                continue
            if len(pins) > 50:  # 高扇出的 net 过滤
                continue
            has_clk_pin = any('CLK' in (pin.get("pin") or "").upper() for pin in pins)
            if has_clk_pin and len(pins) > 50:  # clock-like nets 过滤
                continue
            filtered_nets.add(net_name)

        # ✅ 关键：后面必须用 filtered_nets（否则上面过滤白写）
        candidate_nets = sorted(filtered_nets, key=lambda nm: net_order.get(nm, 10**18))

        hyperedges = []
        for net_name in candidate_nets:
            pins = self.parser.nets.get(net_name, [])
            if not pins:
                continue

            # 这里用“有序去重”（dict 保持插入顺序），等价替代 list 查重 O(k^2)
            ordered_unique = {}
            for pin in pins:
                node_name = pin.get("node")
                if node_name in self.parser.node_name_to_idx:
                    global_idx = self.parser.node_name_to_idx[node_name]
                    if global_idx in node_set:
                        local_idx = old_to_new[global_idx]
                        ordered_unique.setdefault(local_idx, None)

            cluster_pins = list(ordered_unique.keys())
            if len(cluster_pins) >= 2:
                hyperedges.append(tuple(cluster_pins))

        return hyperedges


# =============================================================================
# 主函数
# =============================================================================

def main():
    import argparse
    
    arg_parser = argparse.ArgumentParser(description='FPGA Clustering Pipeline with GIFT')
    arg_parser.add_argument('--benchmark_dir', type=str, required=True,
                           help='FPGA benchmark directory')
    arg_parser.add_argument('--output_dir', type=str, default='./output',
                           help='Output directory')
    arg_parser.add_argument('--aux_file', type=str, default=None,
                           help='.aux file name')
    arg_parser.add_argument('--min_cluster_size', type=int, default=10,
                           help='Minimum cluster size')
    arg_parser.add_argument('--resolution', type=float, default=1.0,
                           help='Louvain resolution parameter')
    arg_parser.add_argument('--gift_scale', type=float, default=0.5,
                           help='GIFT initial position distribution range')
    arg_parser.add_argument('--use_new_filter', action='store_true',
                           help='Use new Laplacian-based filter instead of mixed filter')
    arg_parser.add_argument('--max_cluster_size', type=int, default=None,
                            help='Maximum cluster size')
    arg_parser.add_argument('--macro_neighbor_depth', type=int, default=-1,
                            help='Neighbor layers around each macro for locked clusters: '
                                 '-1=no macro locking, 0=macro only, 1=1-hop neighbors (default), 2=2-hop, ...')
    args = arg_parser.parse_args()
    
    pipeline = FPGAClusteringPipeline(
        benchmark_dir=args.benchmark_dir,
        output_dir=args.output_dir
    )
    print("[run_complete_flow] args.max_cluster_size =", args.max_cluster_size)
    # 以及你真正传进去的值（如果你用 kwargs 组装）
    print("[run_complete_flow] calling run_pipeline with max_cluster_size =", args.max_cluster_size)
    pipeline.run_pipeline(
        aux_file=args.aux_file,
        min_cluster_size=args.min_cluster_size,
        louvain_resolution=args.resolution,
        gift_scale=args.gift_scale,
        use_mixed_filter=not args.use_new_filter,
        max_cluster_size=args.max_cluster_size,
        macro_neighbor_depth=args.macro_neighbor_depth
    )


if __name__ == '__main__':
    main()
