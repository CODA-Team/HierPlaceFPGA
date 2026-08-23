#!/usr/bin/env python3
"""
Cluster-Level Placement Integration Module (Fixed Nodes Support)
=================================================================

修改说明：
1. cluster-level placement 阶段：
   - .nodes 文件包含 cluster 虚拟节点 + 原始 fixed 节点
   - .pl 文件包含 cluster 随机位置 + 原始 fixed 节点位置 (带 FIXED 标记)
   
2. cluster 内随机撒点阶段：
   - fixed 节点不参与随机位置分配
   - 保持原始固定位置

Author: Cluster Placement Integration Tool
"""

import os
import re
import json
import shutil
import argparse
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
from scipy.sparse import csr_matrix, lil_matrix, coo_matrix
import subprocess
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.sparse import coo_matrix
from collections import Counter
import math

MODULE_ROOT = os.path.abspath(os.path.dirname(__file__))


def _cluster_dreamplace_cell_type(cell_type: str) -> str:
    """Map public_release cell names to DREAMPlaceFPGA-supported primitive names."""
    mapping = {
        "DSP": "DSP48E2",
        "RAMA": "RAMB36E2",
        "RAMB": "RAMB36E2",
        "IOA": "IBUF",
        "IOB": "OBUF",
        "GCLK": "BUFGCE",
        "IPPIN": "IBUF",
        "SEQ": "FDRE",
        "CARRY4": "LUT6",
        "LUT6X": "LUT6",
        "F7MUX": "LUT6",
        "F8MUX": "LUT6",
        "DRAM": "LUT6",
    }
    return mapping.get(cell_type, cell_type)


def _cluster_dreamplace_site_type(site_type: str) -> str:
    """Map real public_release site classes onto DREAMPlaceFPGA-supported site tokens."""
    if site_type == "PLB":
        return "SLICE"
    if site_type in {"RAMA", "RAMB"}:
        return "BRAM"
    if site_type in {"IOA", "IOB", "GCLK", "IPPIN"}:
        return "IO"
    return site_type


def _resolve_module_path(path: Optional[str]) -> Optional[str]:
    if path is None or os.path.isabs(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(MODULE_ROOT, path))


_OVERFLOW_LINE_RE = re.compile(r"iter:\s*(\d+).*?Overflow\s*\[([^\]]+)\]")
_TARGET_OVERFLOW_RE = re.compile(r"targetOverflow=\[([^\]]+)\]")


def _parse_float_vector(text: str):
    return [float(x) for x in re.split(r"[\s,]+", text.strip()) if x]


def _report_dreamplace_convergence(log_file: str, label: str) -> None:
    if not log_file or not os.path.exists(log_file):
        return
    last_iter = None
    last_overflow = None
    target = None
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = _OVERFLOW_LINE_RE.search(line)
            if m:
                last_iter = int(m.group(1))
                last_overflow = _parse_float_vector(m.group(2))
            m = _TARGET_OVERFLOW_RE.search(line)
            if m:
                target = _parse_float_vector(m.group(1))
    if last_overflow is None:
        return
    if target is not None and len(target) >= len(last_overflow):
        converged = all(o <= t + 1e-6 for o, t in zip(last_overflow, target))
        print(f"  {label} final iter: {last_iter}, overflow: {last_overflow}, target: {target}, converged: {converged}")
        if not converged:
            print(f"  Warning: {label} stopped at the configured iteration budget before reaching target overflow.")
    else:
        print(f"  {label} final iter: {last_iter}, overflow: {last_overflow} (target not found in log)")


def plot_cluster_scatter(
    node_positions,     # Dict[int, (x,y,z)]  来自 generate_full_placement
    builder,            # ClusterHypergraphBuilder (integrator._builder)
    node_names,         # List[str]
    fixed_nodes=None,   # Dict[name, (x,y,z)]
    chip_width=None,
    chip_height=None,
    color_by="subcluster",   # "subcluster" 或 "louvain"
    out_png=None,
    show=True,
    point_size=1,
    alpha=0.8
):
    fixed_nodes = fixed_nodes or {}

    # 1) 收集 movable 点 (x,y) + label
    xs, ys, labels = [], [], []
    for gidx, (x, y, _z) in node_positions.items():
        sc_idx = builder.node_to_subcluster.get(gidx, None)
        if sc_idx is None:
            continue

        if color_by == "louvain":
            louvain_id = builder.subclusters[sc_idx][0]  # (louvain_id, sub_id, indices)
            label = int(louvain_id)
        else:
            label = int(sc_idx)

        xs.append(float(x))
        ys.append(float(y))
        labels.append(label)

    xs = np.array(xs)
    ys = np.array(ys)
    labels = np.array(labels, dtype=int)

    # 2) 画图
    plt.figure(figsize=(10, 8))
    if len(xs) > 0:
        # 用 label 做颜色映射：同 label 同色
        plt.scatter(xs, ys, c=labels, cmap="hsv", s=point_size, alpha=alpha, linewidths=0)

    # 3) 叠加 fixed 节点（黑色叉号）
    if fixed_nodes:
        fx = [v[0] for v in fixed_nodes.values()]
        fy = [v[1] for v in fixed_nodes.values()]
        plt.scatter(fx, fy, marker="x", s=30, linewidths=1.2, c="k", alpha=0.9, label="fixed")

    # 4) 画芯片边界（可选）
    if chip_width is not None and chip_height is not None:
        plt.xlim(0, chip_width)
        plt.ylim(0, chip_height)
        # 让坐标更像平面布局（可选）：注释掉也行
        # plt.gca().invert_yaxis()

    plt.title(f"Placement scatter (color_by={color_by})")
    plt.xlabel("x")
    plt.ylabel("y")
    plt.grid(True, alpha=0.2)
    if fixed_nodes:
        plt.legend(loc="best")

    if out_png:
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
        plt.savefig(out_png, dpi=200, bbox_inches="tight")
        print(f"[Viz] saved -> {out_png}")

    if show:
        plt.show()
    else:
        plt.close()

def plot_cluster_boxes(
    cluster_positions: Dict[int, Tuple[float, float]],
    cluster_boxes: Dict[int, Tuple[float, float, float]],  # idx -> (w,h,area)
    fixed_nodes=None,
    chip_width=None,
    chip_height=None,
    out_png=None,
    show=True,
    box_alpha=0.25,
    draw_centers=True,
):
    fixed_nodes = fixed_nodes or {}

    plt.figure(figsize=(10, 8))
    ax = plt.gca()

    # 画每个 cluster 方块
    for idx, (cx, cy) in cluster_positions.items():
        w, h, _area = cluster_boxes.get(idx, (1.0, 1.0, 1.0))
        x0 = cx - w / 2.0
        y0 = cy - h / 2.0

        rect = Rectangle(
            (x0, y0),
            w,
            h,
            fill=True,
            alpha=box_alpha,
            linewidth=0.8,
        )
        ax.add_patch(rect)

        if draw_centers:
            ax.scatter([cx], [cy], s=5, c="tab:blue")

    # fixed 节点（黑叉）
    if fixed_nodes:
        fx = [v[0] for v in fixed_nodes.values()]
        fy = [v[1] for v in fixed_nodes.values()]
        ax.scatter(fx, fy, marker="x", s=30, linewidths=1.2, c="k", alpha=0.9, label="fixed")

    if chip_width is not None and chip_height is not None:
        ax.set_xlim(0, chip_width)
        ax.set_ylim(0, chip_height)

    ax.set_title("Cluster placement (boxes from cluster_node_sizes.json)")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(True, alpha=0.2)
    if fixed_nodes:
        ax.legend(loc="best")

    if out_png:
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
        plt.savefig(out_png, dpi=200, bbox_inches="tight")
        print(f"[Viz] saved -> {out_png}")

    if show:
        plt.show()
    else:
        plt.close()
# =============================================================================
# Part 1: 单元面积计算
# =============================================================================

class CellAreaCalculator:
    """
    FPGA单元面积计算器（对齐 DREAMPlaceFPGA 的 site-area 口径）
    """

    DEFAULT_AREAS = {
        # Align with DREAMPlaceFPGA PlaceDBFPGA.initialize():
        # LUT/FF: filler_size_x = filler_size_y = sqrt(0.125) => area = 0.125
        # DSP   : 1.0 x 2.5 => area = 2.5
        # RAM   : 1.0 x 5.0 => area = 5.0
        # IO    : DREAMPlaceFPGA counts each terminal as 1.0 area
        'LUT1': 0.125, 'LUT2': 0.125, 'LUT3': 0.125,
        'LUT4': 0.125, 'LUT5': 0.125, 'LUT6': 0.125,
        'FDRE': 0.125,
        # CARRY8 在 slice 资源里；为了和 LUT/FF 同一口径，按 0.125 处理
        'CARRY8': 0.125,
        'DSP48E2': 2.5,
        'RAMB36E2': 5.0,
        'IBUF': 1.0, 'OBUF': 1.0, 'BUFGCE': 1.0
    }

    def __init__(self, custom_areas: Optional[Dict[str, float]] = None):
        self.areas = self.DEFAULT_AREAS.copy()
        if custom_areas:
            self.areas.update(custom_areas)

    def get_cell_area(self, cell_type: str) -> float:
        """Return cell area in DREAMPlaceFPGA 'site-area' convention."""
        if cell_type in self.areas:
            return float(self.areas[cell_type])

        # prefix-based fallback (covers LUT6, FDRE*, RAMB*, DSP48*, etc.)
        if cell_type.startswith("LUT"):
            return 0.125
        if cell_type.startswith("FDRE") or cell_type.startswith("FDSE") or cell_type.startswith("FDCE"):
            return 0.125
        if cell_type.startswith("CARRY"):
            return 0.125
        if cell_type.startswith("DSP"):
            return 2.5
        if cell_type.startswith("RAMB"):
            return 5.0
        if cell_type.startswith("IBUF") or cell_type.startswith("OBUF") or cell_type.startswith("BUFG"):
            return 1.0

        return 1.0

    def compute_cluster_area(self, cell_types: List[str]) -> float:
        total = 0.0
        for ct in cell_types:
            total += self.get_cell_area(ct)
        # 最小也不该强行抬到 1.0；按一颗 LUT/FF 的 0.125 做下限即可
        return max(total, 0.125)


# =============================================================================
# Part 2: Cluster级别超图构建
# =============================================================================

class ClusterHypergraphBuilder:
    """
    构建cluster级别的超图
    
    【重要修改】: 
    - 新增 fixed_nodes 参数，记录固定节点名称集合
    - fixed 节点不属于任何 subcluster，单独处理
    """
    
    def __init__(self, 
                 node_names: List[str],
                 node_types: Dict[str, str],
                 nets: Dict[str, List[Dict]],
                 cluster_layouts: Dict,
                 clustering_results: Dict,
                 fixed_nodes: Optional[Dict[str, Tuple[float, float, int]]] = None):
        """
        Args:
            node_names: 节点名称列表
            node_types: 节点类型 {node_name: cell_type}
            nets: 网络信息 {net_name: [{node: ..., pin: ...}, ...]}
            cluster_layouts: Louvain cluster布局信息
            clustering_results: SpecPart sub-cluster结果
            fixed_nodes: 固定节点 {name: (x, y, z)}  【新增】
        """
        self.node_names = node_names
        self.node_types = node_types
        self.nets = nets
        self.cluster_layouts = cluster_layouts
        self.clustering_results = clustering_results
        self.fixed_nodes = fixed_nodes or {}
        
        # 固定节点名称集合
        self.fixed_node_names = set(self.fixed_nodes.keys())
        
        # 构建映射
        self.node_name_to_idx = {name: idx for idx, name in enumerate(node_names)}
        
        # Sub-cluster信息
        self.subclusters = []  # [(louvain_id, sub_id, [global_indices])]
        self.subcluster_areas = []
        self.node_to_subcluster = {}  # global_idx -> subcluster_idx
        
        self._build_subcluster_mapping()
    
    def _build_subcluster_mapping(self):
        """构建sub-cluster到节点的映射（排除fixed节点）"""
        area_calc = CellAreaCalculator()
        subcluster_idx = 0
        
        for louvain_id, layout_info in sorted(self.cluster_layouts.items()):
            global_indices = layout_info['node_indices']
            
            # 获取sub-clusters
            if louvain_id in self.clustering_results:
                sub_clusters = self.clustering_results[louvain_id].get('clusters', [])
                
                if len(sub_clusters) > 0:
                    for sub_id, local_indices in enumerate(sub_clusters):
                        # 将局部索引转换为全局索引，排除fixed节点
                        global_sub_indices = []
                        for local_idx in local_indices:
                            if local_idx < len(global_indices):
                                gidx = global_indices[local_idx]
                                node_name = self.node_names[gidx]
                                # 【修改】跳过fixed节点
                                if node_name not in self.fixed_node_names:
                                    global_sub_indices.append(gidx)
                        
                        if len(global_sub_indices) > 0:
                            # 计算面积
                            cell_types = []
                            for gidx in global_sub_indices:
                                name = self.node_names[gidx]
                                if name in self.node_types:
                                    cell_types.append(self.node_types[name])
                            
                            area = area_calc.compute_cluster_area(cell_types)
                            
                            self.subclusters.append((louvain_id, sub_id, global_sub_indices))
                            self.subcluster_areas.append(area)
                            
                            for gidx in global_sub_indices:
                                self.node_to_subcluster[gidx] = subcluster_idx
                            
                            subcluster_idx += 1
                    continue
            
            # 如果没有sub-cluster信息，将整个Louvain cluster作为一个sub-cluster（排除fixed节点）
            movable_indices = []
            cell_types = []
            for gidx in global_indices:
                name = self.node_names[gidx]
                # 【修改】跳过fixed节点
                if name not in self.fixed_node_names:
                    movable_indices.append(gidx)
                    if name in self.node_types:
                        cell_types.append(self.node_types[name])
            
            if len(movable_indices) > 0:
                area = area_calc.compute_cluster_area(cell_types)
                
                self.subclusters.append((louvain_id, -1, movable_indices))
                self.subcluster_areas.append(area)
                
                for gidx in movable_indices:
                    self.node_to_subcluster[gidx] = subcluster_idx
                
                subcluster_idx += 1
        
        print(f"[Cluster Hypergraph] Built {len(self.subclusters)} sub-clusters (movable only)")
        print(f"[Cluster Hypergraph] Fixed nodes: {len(self.fixed_node_names)} (excluded from clusters)")
    def report_subcluster_resource_mix(
        self,
        topk: int = 30,
        out_json: str = None,
        verbose: bool = True,
    ):
        """
        统计每个 sub-cluster 的资源构成，并用 SLICE(16 LUT/16 FF/1 CARRY8)估算可装入的 CLB 数。
        """
        def cat(cell_type: str) -> str:
            ct = (cell_type or "").upper()
            if ct.startswith("LUT"):
                return "LUT"
            if ct.startswith("FD"):  # FDRE/FDCE/...
                return "FF"
            if "CARRY" in ct:
                return "CARRY8"
            if "DSP" in ct:
                return "DSP"
            if "RAMB" in ct or "BRAM" in ct:
                return "BRAM"
            if ct in ("IBUF", "OBUF", "BUFGCE"):
                return "IO"
            return "OTHER"

        reports = []
        for sc_idx, (louvain_id, sub_id, gidx_list) in enumerate(self.subclusters):
            counts = Counter()
            raw_types = []
            for gidx in gidx_list:
                name = self.node_names[gidx]
                t = self.node_types.get(name, None)
                if t is None:
                    continue
                raw_types.append(t)
                counts[cat(t)] += 1

            lut = counts["LUT"]
            ff = counts["FF"]
            carry = counts["CARRY8"]

            # 估算需要的 slice 数（像 CLB 的约束）
            if (lut + ff + carry) > 0:
                n_slice = int(math.ceil(max(lut / 16.0, ff / 16.0, carry / 1.0)))
                n_slice = max(n_slice, 1)
                lut_util = lut / (n_slice * 16.0)
                ff_util = ff / (n_slice * 16.0)
                carry_util = carry / (n_slice * 1.0)
            else:
                n_slice = 0
                lut_util = ff_util = carry_util = 0.0

            n_cells = len(gidx_list)
            rep = {
                "sc_idx": sc_idx,
                "louvain_id": int(louvain_id),
                "sub_id": int(sub_id),
                "n_cells": int(n_cells),
                "counts": dict(counts),
                "slice_need_est": int(n_slice),
                "slice_util": {
                    "lut_util": float(lut_util),
                    "ff_util": float(ff_util),
                    "carry_util": float(carry_util),
                },
            }
            reports.append(rep)

        # 排序：优先看“slice_need 大但利用率低/极不平衡”的
        def score(r):
            u = r["slice_util"]
            # 惩罚利用率低 + slice 很大
            return (r["slice_need_est"], -(u["lut_util"] + u["ff_util"] + u["carry_util"]))

        reports_sorted = sorted(reports, key=score, reverse=True)

        if verbose:
            print("\n[Subcluster Resource Mix] (top {})".format(min(topk, len(reports_sorted))))
            for r in reports_sorted[:topk]:
                c = r["counts"]
                u = r["slice_util"]
                print(
                    f"  sc={r['sc_idx']:4d} lou={r['louvain_id']:4d} sub={r['sub_id']:3d} "
                    f"cells={r['n_cells']:5d} slice_need~{r['slice_need_est']:3d} | "
                    f"LUT={c.get('LUT',0):5d} FF={c.get('FF',0):5d} CARRY8={c.get('CARRY8',0):4d} "
                    f"DSP={c.get('DSP',0):3d} BRAM={c.get('BRAM',0):3d} IO={c.get('IO',0):3d} OTHER={c.get('OTHER',0):3d} | "
                    f"util(lut,ff,car)=({u['lut_util']:.2f},{u['ff_util']:.2f},{u['carry_util']:.2f})"
                )

        if out_json:
            with open(out_json, "w") as f:
                json.dump(reports_sorted, f, indent=2)
            print(f"[Subcluster Resource Mix] saved -> {out_json}")

        return reports_sorted

    def build_cluster_hyperedges(self) -> Tuple[List[Tuple], List[float]]:
        """
        构建cluster级别的超边
        
        【修改说明】:
        - fixed节点不属于任何cluster，但可能参与网络连接
        - 对于包含fixed节点的网络，我们仍然构建cluster间的超边
        """
        hyperedges = []
        weights = []
        
        for net_name, pins in self.nets.items():
            connected_subclusters = set()
            
            for pin_info in pins:
                node_name = pin_info['node'] if isinstance(pin_info, dict) else pin_info
                
                if node_name in self.node_name_to_idx:
                    gidx = self.node_name_to_idx[node_name]
                    if gidx in self.node_to_subcluster:
                        connected_subclusters.add(self.node_to_subcluster[gidx])
            
            if len(connected_subclusters) >= 2:
                hyperedges.append(tuple(sorted(connected_subclusters)))
                weights.append(1.0)
        
        # 合并重复的超边
        edge_weight_map = defaultdict(float)
        for hedge, w in zip(hyperedges, weights):
            edge_weight_map[hedge] += w
        
        final_hyperedges = list(edge_weight_map.keys())
        final_weights = list(edge_weight_map.values())
        
        print(f"[Cluster Hypergraph] Generated {len(final_hyperedges)} cluster-level hyperedges")
        
        return final_hyperedges, final_weights
    
    def build_cluster_adjacency(cluster_hyperedges, n_clusters, weight=1.0):
        """
        Build cluster-level adjacency from hyperedges using COO batch accumulation.
        Interface/output stays the same: returns csr_matrix (n_clusters x n_clusters).
        """
        import numpy as np

        rows = []
        cols = []
        data = []

        w = float(weight)

        for hedge in cluster_hyperedges:
            verts = np.asarray(list(set(hedge)), dtype=np.int64)
            k = int(verts.size)
            if k <= 1:
                continue

            iu, ju = np.triu_indices(k, k=1)
            r = verts[iu]
            c = verts[ju]

            rows.extend(r.tolist())
            cols.extend(c.tolist())
            data.extend((w,) * r.size)

            rows.extend(c.tolist())
            cols.extend(r.tolist())
            data.extend((w,) * r.size)

        A = coo_matrix((data, (rows, cols)), shape=(n_clusters, n_clusters))
        A.sum_duplicates()
        return A.tocsr()


# =============================================================================
# Part 3: Cluster级别Placement生成器
# =============================================================================

class ClusterPlacementGenerator:
    """
    生成Cluster级别的placement benchmark文件
    
    【重要修改】:
    - .nodes 文件包含: cluster虚拟节点 + fixed节点
    - .pl 文件包含: cluster随机位置 + fixed节点原始位置(带FIXED标记)
    """
    
    def __init__(self, 
                 hypergraph_builder: ClusterHypergraphBuilder,
                 chip_width: int,
                 chip_height: int,
                 output_dir: str,
                 benchmark_dir: str,
                 max_fanout: Optional[int] = None,
                 utilization: float = 0.8,
                 place_density_lb_addon: Optional[float] = None,
                 fixed_nodes: Optional[Dict[str, Tuple[float, float, int]]] = None,
                 node_types: Optional[Dict[str, str]] = None):
        """
        Args:
            hypergraph_builder: ClusterHypergraphBuilder实例
            chip_width: 芯片宽度
            chip_height: 芯片高度
            output_dir: 输出目录
            benchmark_dir: 原始benchmark目录
            fixed_nodes: 固定节点 {name: (x, y, z)}  【新增】
            node_types: 节点类型 {name: type}  【新增，用于获取fixed节点的类型】
        """
        self.builder = hypergraph_builder
        self.chip_width = chip_width
        self.chip_height = chip_height
        self.utilization = float(utilization) if (utilization is not None and float(utilization) > 0.0) else 0.8
        # ✅ 新增：PLACE_DENSITY_LB_ADDON 风格控制参数（不为空则用它算 utilization）
        self.place_density_lb_addon = None if place_density_lb_addon is None else float(place_density_lb_addon)

        # ✅ 新增：把最终算出来的 density/util 记下来，供后续 scatter / 生成初始 placement 使用
        self.utilization_used = None
        self.place_density_lb = None
        self.output_dir = output_dir
        self.benchmark_dir = benchmark_dir
        self.fixed_nodes = fixed_nodes or {}
        self.node_types = node_types or {}
        self.max_fanout = max_fanout
        # 虚拟节点映射
        self.virtual_nodes = {}
        self.cluster_node_size_file = ""
        self.subcluster_to_virtual = {}
        self.cluster_net_weight_file = ""
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_cluster_nodes(self) -> str:
        """
        生成.nodes文件
        
        【重要修改】:
        - 包含 cluster 虚拟节点
        - 包含 fixed 节点（使用原始类型）
        """
        nodes_file = os.path.join(self.output_dir, "cluster_design.nodes")
        
        anchor_name = "DUMMY_ANCHOR"   # ← 提前定义

        # 读取 benchmark design.lib 的 CELL 名称，后续保证 .nodes 里的类型在 .lib 中可解析
        lib_cell_types = set()
        src_lib = os.path.join(self.benchmark_dir, "design.lib")
        if os.path.exists(src_lib):
            try:
                with open(src_lib, "r", encoding="utf-8", errors="ignore") as lf:
                    for line in lf:
                        line = line.strip()
                        if line.startswith("CELL "):
                            parts = line.split()
                            if len(parts) >= 2:
                                lib_cell_types.add(parts[1])
            except Exception as e:
                print(f"[Warn] Failed to parse {src_lib}: {e}")
        # cluster_design.lib sanitizes parser-reserved public_release cell names
        # (currently CELL DSP -> CELL DSP48E2), so allow nodes to use the alias.
        for ct in list(lib_cell_types):
            lib_cell_types.add(_cluster_dreamplace_cell_type(ct))

        def _map_type_to_available(raw_type: str, fallback_type: str) -> str:
            """Map a desired type to an available CELL type in design.lib."""
            if not raw_type:
                return fallback_type
            compat_type = _cluster_dreamplace_cell_type(raw_type)
            if compat_type != raw_type:
                if not lib_cell_types or compat_type in lib_cell_types or raw_type in lib_cell_types:
                    return compat_type
            if not lib_cell_types or raw_type in lib_cell_types:
                return raw_type

            # prefix match (covers e.g. DSP48E2 vs DSP48E248E2 naming differences)
            for ct in lib_cell_types:
                if ct.startswith(raw_type) or raw_type.startswith(ct):
                    return ct

            # class-based fallback
            if raw_type.startswith("DSP"):
                for ct in sorted(lib_cell_types):
                    if ct.startswith("DSP"):
                        return ct
            if raw_type.startswith(("RAMA", "RAMB")) or raw_type.startswith("M"):
                for ct in sorted(lib_cell_types):
                    if ct.startswith(("RAMA", "RAMB")) or ct.startswith("M"):
                        return ct

            return fallback_type

        def _infer_default_cluster_cell_type() -> str:
            """Pick a default movable cluster type that is present in design.lib."""
            node_type_counts = Counter(self.node_types.values())
            skip_prefixes = ("IBUF", "OBUF", "BUFG", "PLL", "EMPTY", "IOA", "IOB", "GCLK", "IPPIN")

            preferred = [
                "LUT6",
                "LUT6X",
                "lcell_comb6",
                "lcell_comb5",
                "lcell_comb4",
                "lcell_comb3",
                "lcell_comb2",
                "lcell_comb1",
                "lcell_comb0",
                "dffeas",
                "FDRE",
            ]
            for ct in preferred:
                if node_type_counts.get(ct, 0) <= 0:
                    continue
                if (not lib_cell_types) or (ct in lib_cell_types):
                    return ct

            for ct, _count in node_type_counts.most_common():
                if any(ct.startswith(p) for p in skip_prefixes):
                    continue
                if (not lib_cell_types) or (ct in lib_cell_types):
                    return ct

            for ct in preferred:
                if ct in lib_cell_types:
                    return ct

            if lib_cell_types:
                return sorted(lib_cell_types)[0]
            return "LUT6"

        default_cluster_cell_type = _infer_default_cluster_cell_type()
        print(
            f"[ClusterType] default_cluster_cell_type={default_cluster_cell_type}, "
            f"lib_cells={len(lib_cell_types)}"
        )
        fixed_anchor_cell_type = next(
            (ct for ct in ("IBUF", "OBUF", "BUFGCE") if (not lib_cell_types) or ct in lib_cell_types),
            default_cluster_cell_type,
        )
        if fixed_anchor_cell_type == default_cluster_cell_type:
            print(
                f"[Warn] No fixed-node anchor type found in design.lib; "
                f"fixed anchors will use {fixed_anchor_cell_type} and may be movable in DREAMPlaceFPGA."
            )
        else:
            print(f"[ClusterType] fixed_anchor_cell_type={fixed_anchor_cell_type}")

        size_scale = 1.0
        min_side = 1.0
        max_side = 200.0
        
        subcluster_areas = self.builder.subcluster_areas

        self.virtual_nodes = {}
        self.subcluster_to_virtual = {}

        # =========================
        # ✅ 新增：place_density_with_lb_addon
        #   1) lb = sum(cluster_area) / placeable_area
        #   2) util_used = lb + (1-lb)*addon + 0.01
        # =========================
        placeable_area = float(self.chip_width) * float(self.chip_height)
        total_cluster_area = float(sum(subcluster_areas)) if subcluster_areas is not None else 0.0
        place_density_lb = (total_cluster_area / placeable_area) if placeable_area > 0 else 0.0
        place_density_lb = max(0.0, min(1.0, place_density_lb))

        if self.place_density_lb_addon is not None:
            addon = float(self.place_density_lb_addon)
            # 可选：对 addon 做范围保护（仿照 Tcl 报错）

            #if addon < 0.0 or addon > 0.99:
                #raise ValueError(f"PLACE_DENSITY_LB_ADDON should be in [0, 0.99], got {addon}")
            util_used = place_density_lb + ((1.0 - place_density_lb) * addon) + 0.01
            #if util_used > 1.0:
                #raise ValueError(
                    #f"Place density exceeds 1.0 (PLACE_DENSITY_LB_ADDON={addon}). "
                    #f"Computed util={util_used}, lb={place_density_lb}"
                #)
        else:
            # fallback：旧逻辑
            util_used = float(self.utilization) if float(self.utilization) > 0.0 else 1.0

        # 记录下来给后续使用（然后 scatter / init placement 也能用同一个util）
        self.utilization_used = float(util_used)
        self.place_density_lb = float(place_density_lb)

        print(f"[Density] place_density_lb={place_density_lb:.6f}, "
            f"addon={self.place_density_lb_addon}, util_used={util_used:.6f}")

        size_json = {
            "nodes": {},
            "unit": "site",
            "utilization": float(util_used),
            "place_density_lb": float(place_density_lb),
            "place_density_lb_addon": self.place_density_lb_addon,
        }
        
        # --- 预计算每个 subcluster 的 cell type ---
        # 对于 locked macro cluster，使用 macro 本身的 cell type（DSP48E2 / RAMB36E2），
        # 使 DREAMPlace 将其归入正确的 fence region（region 2 或 3）。
        # 对于普通 cluster，使用在 .lib 中可解析的默认逻辑类型。
        def _resolve_cluster_cell_type(sc_idx):
            louvain_id, _sub_id, global_indices = self.builder.subclusters[sc_idx]
            layout_info = self.builder.cluster_layouts.get(louvain_id, {})
            if not layout_info.get("locked") or layout_info.get("lock_type") != "macro":
                return default_cluster_cell_type
            # 在 locked macro cluster 的节点中找到 macro 的 cell type
            for gidx in global_indices:
                name = self.builder.node_names[gidx]
                ct = self.builder.node_types.get(name, "")
                if ct.startswith("DSP"):
                    return _map_type_to_available(ct, default_cluster_cell_type)
                if ct.startswith(("RAMA", "RAMB")):
                    return _map_type_to_available(ct, default_cluster_cell_type)
            # 也检查 cluster 中所有节点（邻居可能在不同 subcluster 中）
            all_indices = layout_info.get("node_indices", [])
            for gidx in all_indices:
                name = self.builder.node_names[gidx]
                ct = self.builder.node_types.get(name, "")
                if ct.startswith("DSP"):
                    return _map_type_to_available(ct, default_cluster_cell_type)
                if ct.startswith(("RAMA", "RAMB")):
                    return _map_type_to_available(ct, default_cluster_cell_type)
            return default_cluster_cell_type

        with open(nodes_file, 'w') as f:
            # 1. 写入 cluster 虚拟节点
            for idx, _ in enumerate(self.builder.subclusters):
                raw_area = float(subcluster_areas[idx]) if idx < len(subcluster_areas) else 1.0
                eff_area = float(raw_area) / float(util_used)
                side = float(np.sqrt(max(eff_area, 1e-12)) * size_scale)
                side = float(np.clip(side, min_side, max_side))

                node_name = f"cluster_{idx}"
                cell_type = _resolve_cluster_cell_type(idx)
                f.write(f"{node_name} {cell_type}\n")
                
                self.virtual_nodes[idx] = [node_name]
                self.subcluster_to_virtual[idx] = 1
                
                size_json["nodes"][node_name] = {"w": side, "h": side, "area": eff_area, "raw_area": raw_area}
                size_json["nodes"][anchor_name] = {"w": 1.0, "h": 1.0, "area": 1.0}
            
            # 2. 【新增】写入 fixed 节点
            for fixed_name in self.fixed_nodes.keys():
                # DREAMPlaceFPGA only treats IO/BUF-like node types as fixed terminals.
                # Use a fixed-compatible anchor type here; original types stay in final_input.
                f.write(f"{fixed_name} {fixed_anchor_cell_type}\n")
           
            # 3) dummy anchor 节点（新增）
            f.write(f"{anchor_name} {fixed_anchor_cell_type}\n")
            size_json["nodes"][anchor_name] = {"w": 1.0, "h": 1.0, "area": 1.0} 
        
        # 写出尺寸文件
        self.cluster_node_size_file = os.path.join(self.output_dir, "cluster_node_sizes.json")
        with open(self.cluster_node_size_file, "w") as f:
            json.dump(size_json, f, indent=2)
        
        print(f"[Generate] {nodes_file}")
        print(f"[Generate] {self.cluster_node_size_file} (node sizes JSON)")
        print(f"  Cluster nodes: {len(self.builder.subclusters)}")
        print(f"  Fixed nodes: {len(self.fixed_nodes)}")
        print(f"  Total nodes in .nodes: {len(self.builder.subclusters) + len(self.fixed_nodes)}")
        
        return nodes_file
    
    def generate_cluster_nets(
        self,
        base_weight: float = 1,
        fixed_cluster_weight: float = 5.0,
        write_weight_files: bool = True,
    ) -> str:
        """
        生成.nets文件 +（可选）生成.weights/.wts文件

        权重策略：
        - 默认 base_weight
        - 如果一个 net 同时包含 fixed 与 cluster_* 端点：fixed_cluster_weight
        """
        nets_file = os.path.join(self.output_dir, "cluster_design.nets")

        orig_nets = self.builder.nets
        node2idx = self.builder.node_name_to_idx
        node2sc  = self.builder.node_to_subcluster
        fixed_set = set(self.fixed_nodes.keys())

        skipped_highfanout = 0
        fixed_pin_count = {fn: 0 for fn in fixed_set}

        net_idx = 0
        net_weights = []  # [(net_name_in_nets, weight)]

        def _is_cluster_inst(inst: str) -> bool:
            return isinstance(inst, str) and inst.startswith("cluster_")

        with open(nets_file, 'w') as f:
            for _orig_net_name, pins in orig_nets.items():
                endpoints = []

                for pin_info in pins:
                    n = pin_info["node"]

                    if n in fixed_set:
                        # Fixed anchors are written as an IO/BUF-compatible type in
                        # cluster_design.nodes; use a pin that is guaranteed to exist
                        # in the sanitized cluster_design.lib for that surrogate type.
                        endpoints.append((n, "I_0"))
                    elif n in node2idx:
                        gidx = node2idx[n]
                        if gidx in node2sc:
                            sc = node2sc[gidx]
                            endpoints.append((f"cluster_{sc}", "I_0"))

                # 去重（按 inst）
                seen = set()
                uniq = []
                for inst, pin in endpoints:
                    if inst not in seen:
                        uniq.append((inst, pin))
                        seen.add(inst)
                endpoints = uniq

                if len(endpoints) < 2:
                    continue

                # max_fanout 过滤
                if self.max_fanout is not None and self.max_fanout > 0 and len(endpoints) > self.max_fanout:
                    skipped_highfanout += 1
                    continue

                out_net_name = f"net_{net_idx}"

                # ====== 新增：给 net 计算权重 ======
                has_fixed = any(inst in fixed_set for inst, _ in endpoints)
                has_cluster = any(_is_cluster_inst(inst) for inst, _ in endpoints)
                w = float(fixed_cluster_weight if (has_fixed and has_cluster) else base_weight)
                net_weights.append((out_net_name, w))
                # ==================================

                f.write(f"net {out_net_name} {len(endpoints)}\n")
                for inst, pin in endpoints:
                    f.write(f"  {inst} {pin}\n")
                    if inst in fixed_pin_count:
                        fixed_pin_count[inst] += 1
                f.write("endnet\n")
                net_idx += 1

            # 兜底 keepalive net：也要写权重（否则 weight 文件对不上）
            anchor_name = "DUMMY_ANCHOR"
            missing = [fn for fn, c in fixed_pin_count.items() if c == 0]
            # ✅ 新增：记录哪些 fixed 通过 keepalive 连到了 anchor
            self.anchor_connected_fixed = list(missing)
            if missing:
                for fn in missing:
                    keep_name = f"fix_keepalive_{fn}"
                    f.write(f"net {keep_name} 2\n")
                    f.write(f"  {fn} I_0\n")
                    f.write(f"  {anchor_name} I_0\n")
                    f.write("endnet\n")

                    # keepalive 本质也是 fixed↔(anchor)，给它一个基础权重即可
                    net_weights.append((keep_name, float(base_weight)))

        print(f"[Generate] {nets_file}")
        print(f"  Generated {net_idx} nets")
        if self.max_fanout is not None and self.max_fanout > 0:
            print(f"  Skipped {skipped_highfanout} nets (fanout > {self.max_fanout})")

        # ====== 新增：写 weights 文件（你给的格式：net_name weight）======
        if write_weight_files:
            weights_path = os.path.join(self.output_dir, "cluster_design.weights")
            wts_path = os.path.join(self.output_dir, "cluster_design.wts")  # 兼容 aux 逻辑

            for path in (weights_path, wts_path):
                with open(path, "w") as wf:
                    for name, w in net_weights:
                        wf.write(f"{name} {w}\n")

            self.cluster_weight_file = weights_path
            print(f"[Generate] {weights_path}")
            print(f"[Generate] {wts_path}")
        # =============================================================

        return nets_file

    
    def generate_cluster_pl(self) -> str:
        """
        生成.pl文件
        
        【说明】:
        - DREAMPlaceFPGA 的 .pl 文件只用于指定固定节点位置
        - cluster 虚拟节点是 movable 的，由 placer 自动初始化
        - 只写入 fixed 节点：复用原始 design.pl 的位置（带 FIXED 标记）
        """
        pl_file = os.path.join(self.output_dir, "cluster_design.pl")
        anchor_name = "DUMMY_ANCHOR"
        with open(pl_file, 'w') as f:
            # 只写入 fixed 节点（原始位置 + FIXED 标记）
            for fixed_name, (x, y, z) in self.fixed_nodes.items():
                f.write(f"{fixed_name} {int(x)} {int(y)} {int(z)} FIXED\n")
            connected = getattr(self, "anchor_connected_fixed", []) or []
            if connected:
                sx = 0.0
                sy = 0.0
                cnt = 0
                for fn in connected:
                    if fn in self.fixed_nodes:
                        x, y, _z = self.fixed_nodes[fn]
                        sx += float(x)
                        sy += float(y)
                        cnt += 1
                if cnt > 0:
                    anchor_x = int(round(sx / cnt))
                    anchor_y = int(round(sy / cnt))
                else:
                    anchor_x = self.chip_width // 2
                    anchor_y = self.chip_height // 2
            else:
                anchor_x = self.chip_width // 2
                anchor_y = self.chip_height // 2

            # clamp 到版图边界，避免越界
            anchor_x = max(0, min(anchor_x, self.chip_width - 1))
            anchor_y = max(0, min(anchor_y, self.chip_height - 1))

            f.write(f"{anchor_name} {anchor_x} {anchor_y} 0 FIXED\n")

            print(f"  DUMMY_ANCHOR @ ({anchor_x},{anchor_y}), connected_fixed={len(connected)}")
                    
        print(f"[Generate] {pl_file}")
        print(f"  Fixed nodes: {len(self.fixed_nodes)}")
        print(f"  Cluster nodes: {len(self.builder.subclusters)} (movable, no initial position)")
        
        return pl_file
    
    def generate_cluster_scl(self) -> str:
        """生成 cluster placement 使用的 .scl。

        优先从转换后的 benchmark/design.scl 复制真实 SITE/RESOURCES/SITEMAP。
        这样 public_release 新架构中的 PLB/DSP/RAMA/RAMB/IO/GCLK 等资源不会在
        cluster-level DREAMPlaceFPGA 阶段被错误简化为全 SLICE。
        """
        scl_file = os.path.join(self.output_dir, "cluster_design.scl")
        src_scl = os.path.join(self.benchmark_dir, "design.scl")

        def _copy_real_scl(src: str, dst: str) -> bool:
            coord_re = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)$")
            raw_lines = open(src, "r", encoding="utf-8", errors="ignore").readlines()

            site_rows = []
            width = height = None
            in_sitemap = False
            raw_site_counts = Counter()
            for raw in raw_lines:
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("SITEMAP"):
                    parts = stripped.split()
                    if len(parts) >= 3:
                        width, height = int(parts[1]), int(parts[2])
                        in_sitemap = True
                    continue
                if stripped in {"END_SITEMAP", "END SITEMAP"}:
                    in_sitemap = False
                    continue
                if in_sitemap:
                    parts = stripped.split()
                    if len(parts) >= 2:
                        m = coord_re.match(parts[0])
                        if m:
                            x, y, st = int(m.group("x")), int(m.group("y")), parts[1]
                        elif len(parts) >= 3:
                            x, y, st = int(parts[0]), int(parts[1]), parts[2]
                        else:
                            continue
                        site_rows.append((x, y, st))
                        raw_site_counts[st] += 1

            public_release_sites = {"PLB", "RAMA", "RAMB", "IOA", "IOB", "GCLK", "IPPIN"}
            needs_compat = any(st in public_release_sites for _x, _y, st in site_rows)

            if not needs_compat:
                in_sitemap = False
                site_entries = 0
                with open(dst, "w", encoding="utf-8") as fout:
                    for raw in raw_lines:
                        stripped = raw.strip()
                        if not stripped:
                            fout.write(raw)
                            continue
                        if stripped.startswith("#"):
                            fout.write(raw)
                            continue

                        if stripped.startswith("SITEMAP"):
                            parts = stripped.split()
                            if len(parts) >= 3:
                                fout.write(f"SITEMAP {parts[1]} {parts[2]}\n")
                                in_sitemap = True
                                continue

                        if stripped in {"END_SITEMAP", "END SITEMAP"}:
                            fout.write("END SITEMAP\n")
                            in_sitemap = False
                            continue

                        if stripped == "END_SITE":
                            fout.write("END SITE\n")
                            continue

                        if in_sitemap:
                            parts = stripped.split()
                            if len(parts) >= 2:
                                m = coord_re.match(parts[0])
                                if m:
                                    fout.write(f"{int(m.group('x'))} {int(m.group('y'))} {parts[1]}\n")
                                    site_entries += 1
                                    continue
                                if len(parts) >= 3:
                                    site_entries += 1
                            fout.write(raw)
                            continue

                        fout.write(raw)

                print(f"[Copy] {src} -> {dst} (real architecture SCL, site_entries={site_entries})")
                return True

            if width is None or height is None:
                raise ValueError(f"No SITEMAP parsed from {src}")

            compat_site_counts = Counter(_cluster_dreamplace_site_type(st) for _x, _y, st in site_rows)
            with open(dst, "w", encoding="utf-8") as fout:
                fout.write("# Generated from public_release design.scl for DREAMPlaceFPGA cluster placement\n")
                fout.write("# Real site coordinates are preserved; unsupported site names are mapped to SLICE/DSP/BRAM/IO.\n")
                fout.write("SITE SLICE\n")
                fout.write("  LUT 16\n")
                fout.write("  FF 16\n")
                fout.write("  CARRY8 1\n")
                fout.write("END SITE\n\n")
                fout.write("SITE DSP\n")
                fout.write("  DSP48E2 1\n")
                fout.write("END SITE\n\n")
                fout.write("SITE BRAM\n")
                fout.write("  RAMB36E2 1\n")
                fout.write("END SITE\n\n")
                fout.write("SITE IO\n")
                fout.write("  IO 64\n")
                fout.write("END SITE\n\n")
                fout.write("RESOURCES\n")
                fout.write("  LUT LUT1 LUT2 LUT3 LUT4 LUT5 LUT6\n")
                fout.write("  FF FDRE\n")
                fout.write("  CARRY8 CARRY8\n")
                fout.write("  DSP48E2 DSP48E2\n")
                fout.write("  RAMB36E2 RAMB36E2\n")
                fout.write("  IO IBUF OBUF BUFGCE\n")
                fout.write("END RESOURCES\n\n")
                fout.write(f"SITEMAP {width} {height}\n")
                for x, y, site_type in site_rows:
                    fout.write(f"{x} {y} {_cluster_dreamplace_site_type(site_type)}\n")
                fout.write("END SITEMAP\n")

            print(
                f"[Copy] {src} -> {dst} "
                f"(real public_release SITEMAP, DREAMPlace-compatible site classes; "
                f"raw={dict(raw_site_counts)}, compat={dict(compat_site_counts)})"
            )
            return True

        if os.path.exists(src_scl):
            try:
                _copy_real_scl(src_scl, scl_file)
                return scl_file
            except Exception as e:
                print(f"[Warn] Failed to copy real SCL {src_scl}: {e}. Falling back to simplified SLICE SCL.")

        with open(scl_file, 'w') as f:
            f.write("SITE SLICE\n")
            f.write("  LUT 16\n")
            f.write("  FF 16\n")
            f.write("  CARRY8 1\n")
            f.write("END SITE\n\n")
            
            f.write("RESOURCES\n")
            f.write("  LUT LUT1 LUT2 LUT3 LUT4 LUT5 LUT6\n")
            f.write("END RESOURCES\n\n")
            
            f.write(f"SITEMAP {self.chip_width} {self.chip_height}\n")
            for x in range(self.chip_width):
                for y in range(self.chip_height):
                    f.write(f"{x} {y} SLICE\n")
            f.write("END SITEMAP\n")
        
        print(f"[Generate] {scl_file}")
        return scl_file
    
    def generate_cluster_lib(self) -> str:
        """生成/拷贝 .lib 文件，并规避 DREAMPlaceFPGA Bookshelf parser 保留字。"""
        lib_file = os.path.join(self.output_dir, "cluster_design.lib")
        src_lib = os.path.join(self.benchmark_dir, "design.lib")
        
        if os.path.exists(src_lib):
            renamed_cells = {}
            cell_order = []
            cell_pins = defaultdict(dict)  # compat_cell -> pin_name -> (direction, suffix)
            current_cell = None

            def _pin_rank(direction: str, suffix: str) -> int:
                if direction != "INPUT":
                    return 10
                if suffix == " CLOCK":
                    return 3
                if suffix == " CTRL":
                    return 2
                return 1

            with open(src_lib, "r", encoding="utf-8", errors="ignore") as fin:
                for raw in fin:
                    stripped = raw.strip()
                    if stripped.startswith("CELL "):
                        parts = stripped.split()
                        raw_cell = parts[1] if len(parts) >= 2 else ""
                        compat_cell = _cluster_dreamplace_cell_type(raw_cell)
                        if compat_cell != raw_cell:
                            renamed_cells[raw_cell] = compat_cell
                        current_cell = compat_cell
                        if compat_cell not in cell_pins:
                            cell_order.append(compat_cell)
                            cell_pins[compat_cell]
                        continue

                    if stripped in {"END_CELL", "END CELL"}:
                        current_cell = None
                        continue

                    if current_cell and stripped.startswith("PIN "):
                        parts = stripped.split()
                        if len(parts) >= 3:
                            pin_name, direction = parts[1], parts[2].upper()
                            attrs = {p.upper() for p in parts[3:]}
                            suffix = ""
                            if direction == "INPUT":
                                if "CLOCK" in attrs:
                                    suffix = " CLOCK"
                                elif "CTRL" in attrs or "RESET" in attrs:
                                    suffix = " CTRL"
                            old = cell_pins[current_cell].get(pin_name)
                            if old is None or _pin_rank(direction, suffix) > _pin_rank(old[0], old[1]):
                                cell_pins[current_cell][pin_name] = (direction, suffix)

            def _pin_sort_key(name: str):
                m = re.match(r"([A-Za-z_]+)(\d+)$", name)
                if m:
                    return (m.group(1), int(m.group(2)))
                return (name, -1)

            with open(lib_file, "w", encoding="utf-8") as fout:
                for cell in cell_order:
                    fout.write(f"CELL {cell}\n")
                    for pin_name in sorted(cell_pins[cell].keys(), key=_pin_sort_key):
                        direction, suffix = cell_pins[cell][pin_name]
                        fout.write(f"  PIN {pin_name} {direction}{suffix}\n")
                    fout.write("END CELL\n\n")
            if renamed_cells:
                print(f"[Copy] {src_lib} -> {lib_file} (cell aliases: {renamed_cells})")
            else:
                print(f"[Copy] {src_lib} -> {lib_file}")
        else:
            open(lib_file, "w").close()
            print(f"[Warn] {src_lib} not found. Created empty {lib_file}.")
        return lib_file
    
    def generate_cluster_aux(self) -> str:
        """生成.aux文件"""
        aux_file = os.path.join(self.output_dir, "cluster_design.aux")
        
        lib_file = os.path.join(self.output_dir, "cluster_design.lib")
        src_lib = os.path.join(self.benchmark_dir, "design.lib")
        if not os.path.exists(lib_file):
            if os.path.exists(src_lib):
                self.generate_cluster_lib()
            else:
                open(lib_file, "w").close()
                print(f"[Warn] Created empty {lib_file}.")
        
        
        aux_list = [
            "cluster_design.nodes",
            "cluster_design.nets",
            "cluster_design.wts" if os.path.exists(os.path.join(self.output_dir, "cluster_design.wts")) else None,
            "cluster_design.pl",
            "cluster_design.scl",
            "cluster_design.lib",
        ]
        aux_list = [x for x in aux_list if x is not None]
        
        with open(aux_file, 'w') as f:
            f.write("design : " + " ".join(aux_list) + "\n")
        
        print(f"[Generate] {aux_file}")
        return aux_file
    
    def generate_cluster_config(self, 
                                gpu: int = 0,
                                iteration: int = 1000,
                                random_seed: int = 1000,
                                net_weight_file: str = "",
                                learning_rate: float = 0.01) -> str:
        """生成DREAMPlaceFPGA配置文件"""
        config = {
            "global_place_sol": "",
            "place_sol": "",
            "aux_input": "cluster_design.aux",
            "cluster_node_size_file": os.path.basename(self.cluster_node_size_file),  # -> cluster_node_sizes.json
            "init_placement_file": "",
            "gpu": gpu,
            "num_threads": 4,
            "num_bins_x": 256,
            "num_bins_y": 256,
            "global_place_stages": [
                {
                    "num_bins_x": 256,
                    "num_bins_y": 256,
                    "iteration": iteration,
                    "learning_rate": learning_rate,
                    "wirelength": "weighted_average",
                    "optimizer": "nesterov"
                }
            ],
            "result_dir": "results",
            "routability_opt_flag": 0,
            "target_density": 1.0,
            "density_weight": 8e-5,
            #"random_seed": 10000,#固定cluster placement种子进行实验
            "random_seed": int(random_seed),
            "scale_factor": 1.0,
            "global_place_flag": 1,
            "legalize_flag": 0,
            "detailed_place_flag": 0,
            "dtype": "float32",
            "deterministic_flag": 1,
            "random_center_init_flag": 1
        }
        # ✅ 新增：写入 net_weight_file（建议写相对路径，跑起来更稳）
        if net_weight_file:
            config["net_weight_file"] = net_weight_file

        os.makedirs(config["result_dir"], exist_ok=True)

        config_file = os.path.join(self.output_dir, "cluster_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"[Generate] {config_file}")
        return config_file
    
    def generate_all(
        self,
        base_weight: float = 0.1,
        fixed_cluster_weight: float = 5.0,
        random_seed: Optional[int] = None,
        iteration: int = 1000,
    ) -> Dict[str, str]:
        """生成所有文件"""
        print("[ClusterPlacementGenerator] Generating all files...")
        print(f"  [Weights] base_weight={base_weight}, fixed_cluster_weight={fixed_cluster_weight}")

        nodes_file = self.generate_cluster_nodes()
        nets_file = self.generate_cluster_nets(
            base_weight=base_weight,
            fixed_cluster_weight=fixed_cluster_weight,
            write_weight_files=True
        )
        pl_file = self.generate_cluster_pl()
        scl_file = self.generate_cluster_scl()
        lib_file = self.generate_cluster_lib()
        aux_file = self.generate_cluster_aux()

        weight_basename = ""
        if hasattr(self, "cluster_weight_file") and self.cluster_weight_file:
            weight_basename = os.path.basename(self.cluster_weight_file)  # cluster_design.weights

        seed_used = int(random_seed) if random_seed is not None else 1000
        config_file = self.generate_cluster_config(
            net_weight_file=weight_basename,
            random_seed=seed_used,
            iteration=int(iteration),
        )

        return {
            'nodes': nodes_file,
            'nets': nets_file,
            'pl': pl_file,
            'scl': scl_file,
            'lib': lib_file,
            'aux': aux_file,
            'config': config_file
        }

# =============================================================================
# Part 4: Cluster位置到单元位置转换
# =============================================================================

class ClusterToNodePlacement:
    """
    将cluster级别的placement结果转换为单元级别的placement
    
    【重要修改】:
    - fixed节点不参与cluster内随机撒点
    - fixed节点保持原始固定位置
    """
    
    def __init__(self,
                 hypergraph_builder: ClusterHypergraphBuilder,
                 chip_width: int,
                 chip_height: int,
                 fixed_nodes: Optional[Dict[str, Tuple[float, float, int]]] = None,
                 utilization: float = 0.8,
                 sigma_ratio: float = 0.9,
                 cluster_node_size_file: Optional[str] = None,
                 scatter_mode: str = "gaussian_circle"):
        self.builder = hypergraph_builder
        self.chip_width = chip_width
        self.chip_height = chip_height
        self.utilization = float(utilization) if (utilization is not None and float(utilization) > 0.0) else 0.8
        self.sigma_ratio = float(sigma_ratio) if (sigma_ratio is not None and np.isfinite(float(sigma_ratio))) else 0.9
        self.fixed_nodes = fixed_nodes or {}
        self.fixed_node_names = set(self.fixed_nodes.keys())
        self.scatter_mode = str(scatter_mode or "gaussian_circle").strip().lower()
    # 【新增】cluster 方块尺寸：idx -> (w, h, area)
        self.cluster_boxes: Dict[int, Tuple[float, float, float]] = {}
        if cluster_node_size_file and os.path.exists(cluster_node_size_file):
            self.cluster_boxes = self._load_cluster_boxes(cluster_node_size_file)
        else:
            # 没有 json 时保持空，后面会 fallback 到 builder.subcluster_areas
            self.cluster_boxes = {}

    def _load_cluster_boxes(self, json_file: str) -> Dict[int, Tuple[float, float, float]]:
        """
        从 cluster_node_sizes.json 读取每个 cluster_{idx} 的 (w, h, area)
        """
        with open(json_file, "r") as f:
            js = json.load(f)

        boxes: Dict[int, Tuple[float, float, float]] = {}
        nodes = js.get("nodes", {})
        for name, info in nodes.items():
            if not isinstance(name, str) or not name.startswith("cluster_"):
                continue
            try:
                idx = int(name.replace("cluster_", "").split("_")[0])
            except Exception:
                continue

            area = float(info.get("area", 1.0))
            w = float(info.get("w", np.sqrt(area)))
            h = float(info.get("h", np.sqrt(area)))

            # 防御一下非法值
            if w <= 0 or h <= 0:
                side = float(np.sqrt(max(area, 1.0)))
                w, h = side, side

            boxes[idx] = (w, h, area)

        return boxes
    def read_cluster_placement(self, pl_file: str) -> Dict[int, Tuple[float, float]]:
        """
        读取cluster placement结果
        
        【说明】: 只读取cluster_*节点的位置，忽略fixed节点
        """
        cluster_pos_list = {}
        
        with open(pl_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 跳过 FIXED 行
                if 'FIXED' in line.upper():
                    continue
                
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    if name.startswith('cluster_'):
                        try:
                            x = float(parts[1])
                            y = float(parts[2])
                            
                            name_parts = name.replace('cluster_', '').split('_')
                            cluster_idx = int(name_parts[0])
                            
                            if cluster_idx not in cluster_pos_list:
                                cluster_pos_list[cluster_idx] = []
                            cluster_pos_list[cluster_idx].append((x, y))
                        except (ValueError, IndexError):
                            continue
        
        # 计算每个cluster的平均位置
        cluster_positions = {}
        for idx, positions in cluster_pos_list.items():
            if positions:
                avg_x = sum(p[0] for p in positions) / len(positions)
                avg_y = sum(p[1] for p in positions) / len(positions)
                cluster_positions[idx] = (avg_x, avg_y)
        
        return cluster_positions
    
    
    def distribute_nodes_in_cluster(self,
                                    cluster_pos: Tuple[float, float],
                                    node_indices: List[int],
                                    seed: int = None,
                                    box_w: Optional[float] = None,     # 仍保留参数，兼容旧调用/可视化
                                    box_h: Optional[float] = None,     # 仍保留参数，兼容旧调用/可视化
                                    cluster_area: Optional[float] = None,
                                    circle_shrink: float = 1.0,        # 1.0 表示圆面积严格等于 cluster_area
                                    sigma_ratio: float = 0.95,         # 高斯标准差 sigma = R * sigma_ratio
                                    max_tries: int = 50,
                                    scatter_mode: Optional[str] = None,
                                ) -> Dict[int, Tuple[float, float, int]]:
        """
        在cluster区域内分配节点位置（仅movable节点）
        功能保持不变：
        1) 截断高斯（集中在中心）优先
        2) 失败则 fallback：均匀圆盘
        3) 再兜底：放中心
        改动点：逐点重试 -> 向量化批量采样（大幅减少 Python 循环开销）
        """
        # 用局部 RNG，避免污染全局 np.random；也方便未来并行
        # 如果 seed 为 None，使用固定默认值 42 确保可复现
        rng = np.random.default_rng(seed if seed is not None else 42)

        positions: Dict[int, Tuple[float, float, int]] = {}
        if not node_indices:
            return positions

        cx, cy = float(cluster_pos[0]), float(cluster_pos[1])

        # clamp center to chip
        cx = max(0.0, min(float(self.chip_width) - 1.0, cx))
        cy = max(0.0, min(float(self.chip_height) - 1.0, cy))

        # area priority: cluster_area -> box_w*box_h -> 1.0
        if cluster_area is None:
            if box_w is not None and box_h is not None:
                cluster_area = float(box_w) * float(box_h)
            else:
                cluster_area = 1.0

        area = float(cluster_area)
        if (not np.isfinite(area)) or area <= 0.0:
            area = 1.0

        # ============ NEW: scatter mode switch ============
        mode = (scatter_mode or self.scatter_mode or "gaussian_circle").strip().lower()

        # 如果要在矩形内均匀撒点：使用 box_w/box_h 作为“原来的矩形”
        # 若 box_w/box_h 不提供，则退化为以 sqrt(area) 为边长的正方形
        if mode in ("uniform_rect", "rect_uniform", "uniform_rectangle"):
            if box_w is None or box_h is None:
                side = float(np.sqrt(max(area, 1e-12)))
                box_w = side
                box_h = side

            bw = float(box_w)
            bh = float(box_h)
            if (not np.isfinite(bw)) or bw <= 0:
                bw = float(np.sqrt(max(area, 1e-12)))
            if (not np.isfinite(bh)) or bh <= 0:
                bh = float(np.sqrt(max(area, 1e-12)))

            x0 = cx - bw / 2.0
            x1 = cx + bw / 2.0
            y0 = cy - bh / 2.0
            y1 = cy + bh / 2.0

            chip_w = float(self.chip_width)
            chip_h = float(self.chip_height)

            n = len(node_indices)
            xs = np.empty(n, dtype=np.float64)
            ys = np.empty(n, dtype=np.float64)
            placed = np.zeros(n, dtype=bool)

            remain = ~placed
            for _ in range(max_tries):
                idx = np.where(remain)[0]
                if idx.size == 0:
                    break
                x = rng.uniform(x0, x1, size=idx.size)
                y = rng.uniform(y0, y1, size=idx.size)
                ok = (x >= 0.0) & (x < chip_w) & (y >= 0.0) & (y < chip_h)
                if np.any(ok):
                    acc = idx[ok]
                    xs[acc] = x[ok]
                    ys[acc] = y[ok]
                    placed[acc] = True
                remain = ~placed

            # 兜底：没放进去的点放中心
            if np.any(~placed):
                idx = np.where(~placed)[0]
                xs[idx] = cx
                ys[idx] = cy
                placed[idx] = True

            for i, gidx in enumerate(node_indices):
                positions[gidx] = (float(xs[i]), float(ys[i]), 0)
            return positions
        # ============ END NEW ============

        # radius from area (circle area = area)
        R = float(np.sqrt(area / np.pi) * float(circle_shrink))

        # too small -> all at center
        if R < 1e-6:
            for gidx in node_indices:
                positions[gidx] = (cx, cy, 0)
            return positions

        chip_w = float(self.chip_width)
        chip_h = float(self.chip_height)

        sigma = max(1e-6, R * float(sigma_ratio))

        n = len(node_indices)
        xs = np.empty(n, dtype=np.float64)
        ys = np.empty(n, dtype=np.float64)
        placed = np.zeros(n, dtype=bool)

        # ----------------------------
        # Stage 1: truncated 2D Gaussian in circle (no circle rejection needed)
        #   radius distribution is Rayleigh(sigma) truncated at R
        # ----------------------------
        # alpha = P(r <= R) for Rayleigh
        alpha = 1.0 - np.exp(-(R * R) / (2.0 * sigma * sigma))
        alpha = max(alpha, 1e-12)  # avoid numerical issue

        remain = ~placed
        for _ in range(max_tries):
            idx = np.where(remain)[0]
            if idx.size == 0:
                break

            u = rng.random(idx.size)
            v = rng.random(idx.size)

            # truncated Rayleigh inverse CDF
            r = sigma * np.sqrt(-2.0 * np.log(1.0 - u * alpha))
            theta = 2.0 * np.pi * v

            x = cx + r * np.cos(theta)
            y = cy + r * np.sin(theta)

            ok = (x >= 0.0) & (x < chip_w) & (y >= 0.0) & (y < chip_h)
            if np.any(ok):
                acc = idx[ok]
                xs[acc] = x[ok]
                ys[acc] = y[ok]
                placed[acc] = True

            remain = ~placed

        # ----------------------------
        # Stage 2: fallback uniform disk (same as your original fallback, but vectorized)
        # ----------------------------
        remain = ~placed
        for _ in range(max_tries):
            idx = np.where(remain)[0]
            if idx.size == 0:
                break

            u = rng.random(idx.size)
            v = rng.random(idx.size)
            r = R * np.sqrt(u)
            theta = 2.0 * np.pi * v

            x = cx + r * np.cos(theta)
            y = cy + r * np.sin(theta)

            ok = (x >= 0.0) & (x < chip_w) & (y >= 0.0) & (y < chip_h)
            if np.any(ok):
                acc = idx[ok]
                xs[acc] = x[ok]
                ys[acc] = y[ok]
                placed[acc] = True

            remain = ~placed

        # ----------------------------
        # Stage 3: last resort -> center
        # ----------------------------
        if np.any(~placed):
            idx = np.where(~placed)[0]
            xs[idx] = cx
            ys[idx] = cy
            placed[idx] = True

        # write back
        for i, gidx in enumerate(node_indices):
            positions[gidx] = (float(xs[i]), float(ys[i]), 0)

        return positions

    def generate_full_placement(self,
                                cluster_positions: Dict[int, Tuple[float, float]],
                                base_seed: int = 42) -> Dict[int, Tuple[float, float, int]]:
        """
        生成完整的单元placement（仅movable节点）
        
        【重要修改】:
        - subclusters 中已经排除了 fixed 节点
        - 这里只生成 movable 节点的位置
        """
        all_positions = {}
        # 创建确定性的 RNG，确保可复现
        rng = np.random.default_rng(base_seed)
        print(f"[DEBUG] Utilization factor used: {self.utilization}")
        for sc_idx, (louvain_id, sub_id, global_indices) in enumerate(self.builder.subclusters):
            if sc_idx not in cluster_positions:
                cx = rng.uniform(0.2 * self.chip_width, 0.8 * self.chip_width)
                cy = rng.uniform(0.2 * self.chip_height, 0.8 * self.chip_height)
            else:
                cx, cy = cluster_positions[sc_idx]
            
            area = self.builder.subcluster_areas[sc_idx]
            seed = base_seed + sc_idx
            
             # 【新增】优先用 cluster_node_sizes.json 的 w/h/area
            if sc_idx in self.cluster_boxes:
                w, h, area = self.cluster_boxes[sc_idx]
                node_positions = self.distribute_nodes_in_cluster(
                    cluster_pos=(cx, cy),
                    node_indices=global_indices,
                    #seed=10000,#固定scatter种子进行实验
                    seed=seed,
                    box_w=w,
                    box_h=h,
                    cluster_area=area,  # 传着也行（只是备用）
                    sigma_ratio=self.sigma_ratio,
                    scatter_mode=self.scatter_mode,
                )
            else:
                # fallback 到 builder.subcluster_areas
                raw_area = self.builder.subcluster_areas[sc_idx]
                area = float(raw_area) / float(self.utilization)
                node_positions = self.distribute_nodes_in_cluster(
                    cluster_pos=(cx, cy),
                    node_indices=global_indices,
                    #seed=10000,#固定scatter种子进行实验
                    seed=seed,
                    cluster_area=area,
                    sigma_ratio=self.sigma_ratio,
                    scatter_mode=self.scatter_mode,
                )

            all_positions.update(node_positions)
        
        print(f"[Generate Full Placement] Generated {len(all_positions)} movable node positions")
        print(f"[Generate Full Placement] Fixed nodes ({len(self.fixed_nodes)}) not included in random scatter")
        
        return all_positions
    
    def write_placement_file(self,
                              positions: Dict[int, Tuple[float, float, int]],
                              node_names: List[str],
                              output_file: str = "movable_init.pl") -> str:
        """
        写入可移动节点的初始placement文件
        
        【说明】: 只写入movable节点，不写入fixed节点
        """
        with open(output_file, 'w') as f:
            for gidx, (x, y, z) in positions.items():
                if gidx < len(node_names):
                    name = node_names[gidx]
                    # 确保不写入fixed节点
                    if name not in self.fixed_node_names:
                        f.write(f"{name} {x:.6f} {y:.6f} {int(z)}\n")
        
        print(f"[Write Placement] {output_file} (movable nodes only, integer coordinates)")
        return output_file
    
    def write_fixed_placement_file(self,
                                    output_file: str = "design.pl") -> str:
        """
        写入固定节点的placement文件
        
        【说明】: 复用原始 design.pl 的 fixed 节点位置
        """
        with open(output_file, 'w') as f:
            for name, (x, y, z) in self.fixed_nodes.items():
                f.write(f"{name} {int(round(x))} {int(round(y))} {int(z)} FIXED\n")
        
        print(f"[Write Placement] {output_file} (fixed nodes only, {len(self.fixed_nodes)} nodes)")
        return output_file


# =============================================================================
# Part 5: 完整流程集成
# =============================================================================

class ClusterPlacementIntegration:
    """
    完整的Cluster Placement集成流程
    
    【关键修改点】:
    1. parse_benchmark() 解析 fixed 节点
    2. run_cluster_placement() 将 fixed_nodes 传给 builder 和 generator
    3. generate_initial_placement() 中 fixed 节点不参与随机撒点
    """
    
    def __init__(self,
                 benchmark_dir: str,
                 output_dir: str,
                 cluster_random_seed: Optional[int] = None):
        """
        Args:
            benchmark_dir: 原始 benchmark 目录
            output_dir: 输出目录
            cluster_random_seed: 统一控制 cluster placement 阶段（以及后续撒点/最终 placement 默认）的随机种子。
                - None: 保持原有默认（内部会 fallback 到 42 / 1000 等默认值）
        """
        self.cluster_random_seed = int(cluster_random_seed) if cluster_random_seed is not None else None
        if self.cluster_random_seed is not None:
            self._set_global_seeds(self.cluster_random_seed)

        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir
        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir
        self.cluster_output_dir = os.path.join(output_dir, "cluster_placement")
        self.final_output_dir = os.path.join(output_dir, "final_placement")
        
        os.makedirs(self.cluster_output_dir, exist_ok=True)
        os.makedirs(self.final_output_dir, exist_ok=True)
        
        self.node_names = []
        self.node_types = {}
        self.nets = {}
        self.fixed_nodes = {}
        self.chip_width = 0
        self.chip_height = 0
    
    def _set_global_seeds(self, seed: int) -> None:
        """Set python/numpy (and optional torch) random seeds for reproducibility."""
        import random
        seed = int(seed)
        random.seed(seed)
        np.random.seed(seed)
        try:
            import torch  # optional
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            # Make cuDNN deterministic if used
            try:
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
            except Exception:
                pass
        except Exception:
            pass

    def parse_benchmark(self):
        """解析原始benchmark文件"""
        # 解析.nodes文件
        for f in os.listdir(self.benchmark_dir):
            if f.endswith('.nodes'):
                nodes_file = os.path.join(self.benchmark_dir, f)
                with open(nodes_file, 'r') as file:
                    for line in file:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            name = parts[0]
                            cell_type = parts[1]
                            self.node_names.append(name)
                            self.node_types[name] = cell_type
                break
        
        # 解析.nets文件
        for f in os.listdir(self.benchmark_dir):
            if f.endswith('.nets'):
                nets_file = os.path.join(self.benchmark_dir, f)
                self._parse_nets(nets_file)
                break
        
        # 解析.pl文件获取固定节点
        for f in os.listdir(self.benchmark_dir):
            if f.endswith('.pl'):
                pl_file = os.path.join(self.benchmark_dir, f)
                self._parse_pl(pl_file)
                break
        
        # 解析.scl文件获取芯片尺寸
        for f in os.listdir(self.benchmark_dir):
            if f.endswith('.scl'):
                scl_file = os.path.join(self.benchmark_dir, f)
                self._parse_scl(scl_file)
                break
        
        print(f"[Parse] {len(self.node_names)} nodes, {len(self.nets)} nets")
        print(f"[Parse] Chip size: {self.chip_width} x {self.chip_height}")
        print(f"[Parse] Fixed nodes: {len(self.fixed_nodes)}")
        
        # 打印一些fixed节点示例
        if self.fixed_nodes:
            sample_fixed = list(self.fixed_nodes.items())[:5]
            print(f"[Parse] Sample fixed nodes:")
            for name, (x, y, z) in sample_fixed:
                print(f"  {name}: ({x}, {y}, {z})")
    
    def _parse_nets(self, nets_file: str):
        """解析.nets文件"""
        current_net = None
        current_pins = []
        
        with open(nets_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if line.startswith('net '):
                    parts = line.split()
                    current_net = parts[1] if len(parts) >= 2 else f"net_{len(self.nets)}"
                    current_pins = []
                elif line == 'endnet':
                    if current_net:
                        self.nets[current_net] = current_pins
                    current_net = None
                    current_pins = []
                elif current_net is not None:
                    parts = line.split()
                    if len(parts) >= 1:
                        current_pins.append({'node': parts[0], 'pin': parts[1] if len(parts) > 1 else 'I'})
    
    def _parse_pl(self, pl_file: str):
        """
        解析.pl文件获取固定节点
        
        【关键】: 正确解析原始 design.pl 中的 FIXED 行
        格式: node_name x y z FIXED
        """
        with open(pl_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 检查是否是 FIXED 行
                if 'FIXED' in line.upper():
                    parts = line.split()
                    if len(parts) >= 4:
                        name = parts[0]
                        try:
                            x = float(parts[1])
                            y = float(parts[2])
                            # z 可能在 FIXED 之前
                            z = 0
                            for i in range(3, len(parts)):
                                if parts[i].upper() == 'FIXED':
                                    break
                                try:
                                    z = int(parts[i])
                                except ValueError:
                                    pass
                            self.fixed_nodes[name] = (x, y, z)
                        except ValueError:
                            continue
    
    def _parse_scl(self, scl_file: str):
        """解析.scl文件获取芯片尺寸"""
        with open(scl_file, 'r') as f:
            for line in f:
                if line.startswith('SITEMAP'):
                    parts = line.split()
                    if len(parts) >= 3:
                        self.chip_width = int(parts[1])
                        self.chip_height = int(parts[2])
                    break
    
    def run_cluster_placement(self,
                               cluster_layouts: Dict,
                               clustering_results: Dict,
                               dreamplace_path: str = None,
                               gpu: int = 0,
                               cluster_random_seed: Optional[int] = None,
                               max_fanout: Optional[int] = None,
                               iteration: int = 1000,
                               base_weight: float = 1.0,
                               fixed_cluster_weight: float = 10.0,
                               place_density_lb_addon: float = 0.0,
                               utilization: float = 0.8) -> str:
        """
        运行cluster级别的placement
        
        【关键修改】:
        - 传入 fixed_nodes 给 ClusterHypergraphBuilder
        - 传入 fixed_nodes 和 node_types 给 ClusterPlacementGenerator
        """
        print("\n" + "=" * 70)
        print("Phase 1: Cluster-Level Global Placement")
        print("=" * 70)
        
        # --- random seed control (from JSON: cluster_random_seed) ---
        if cluster_random_seed is not None:
            self.cluster_random_seed = int(cluster_random_seed)
            self._set_global_seeds(self.cluster_random_seed)
        seed_used = int(self.cluster_random_seed) if self.cluster_random_seed is not None else 1000

        # 构建cluster超图（传入fixed_nodes）
        print("\n[1.1] Building cluster hypergraph...")
        builder = ClusterHypergraphBuilder(
            node_names=self.node_names,
            node_types=self.node_types,
            nets=self.nets,
            cluster_layouts=cluster_layouts,
            clustering_results=clustering_results,
            fixed_nodes=self.fixed_nodes  # 【新增】
        )
        builder.report_subcluster_resource_mix(
            topk=50,
            out_json=os.path.join(self.cluster_output_dir, "subcluster_resource_mix.json"),
            verbose=True
        )
        # 生成cluster benchmark文件（传入fixed_nodes和node_types）
        print("\n[1.2] Generating cluster benchmark files...")
        generator = ClusterPlacementGenerator(
            hypergraph_builder=builder,
            chip_width=self.chip_width,
            chip_height=self.chip_height,
            output_dir=self.cluster_output_dir,
            benchmark_dir=self.benchmark_dir,
            max_fanout=max_fanout,          
            utilization=utilization,
            place_density_lb_addon=place_density_lb_addon,  #  新增
            fixed_nodes=self.fixed_nodes,  # 【新增】
            node_types=self.node_types     # 【新增】
        )
        
        print(f"[ClusterPlacement] net weights: base_weight={base_weight}, fixed_cluster_weight={fixed_cluster_weight}")

        files = generator.generate_all(
            base_weight=base_weight,
            fixed_cluster_weight=fixed_cluster_weight,
            random_seed=seed_used,
            iteration=int(iteration),
        )
        self._cluster_utilization_used = getattr(generator, "utilization_used", None)
        config_file = files["config"]  # ✅ 用 generate_all 生成的那份（带 net_weight_file）
        config_basename = os.path.basename(config_file)
        dreamplace_path = _resolve_module_path(dreamplace_path)

        # 运行DREAMPlaceFPGA
        if dreamplace_path and os.path.exists(dreamplace_path):
            print("\n[1.3] Running DREAMPlaceFPGA for cluster placement...")
            placer_script = os.path.join(dreamplace_path, "dreamplacefpga", "Placer.py")
            
            if os.path.exists(placer_script):
                log_file = os.path.join(self.cluster_output_dir, "cluster_placement.log")
                cmd = f"python {placer_script} {config_basename}"
                print(f"  Command: {cmd}")
                print(f"  Log: {log_file}")
                try:
                    env = os.environ.copy()
                    if getattr(generator, "cluster_node_size_file", ""):
                        env["CLUSTER_NODE_SIZE_FILE"] = generator.cluster_node_size_file
                    
                    with open(log_file, "w") as lf:
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            text=True,
                            timeout=6000,
                            cwd=self.cluster_output_dir,
                            env=env,
                            stdout=lf,
                            stderr=lf,
                        )

                    if result.returncode == 0:
                        print("  DREAMPlaceFPGA completed successfully")
                        _report_dreamplace_convergence(log_file, "Cluster placement")
                    else:
                        print(f"  Warning: DREAMPlaceFPGA returned {result.returncode}")
                        print(f"  Check log file: {log_file}")
                except subprocess.TimeoutExpired:
                    print("  Warning: DREAMPlaceFPGA timed out")
                    print(f"  Check log file: {log_file}")
                except Exception as e:
                    print(f"  Warning: Failed to run DREAMPlaceFPGA: {e}")
                    print(f"  Check log file: {log_file}")
        else:
            print("\n[1.3] Skipping DREAMPlaceFPGA (path not provided)")
            print("  Using initial random placement")
        
        # 查找placement结果
        design_name = "cluster_design"
        possible_gp_files = [
            os.path.join(self.cluster_output_dir, "cluster_design.final.pl"),
            os.path.join(self.cluster_output_dir, "results", "cluster_design.final.pl"),
            os.path.join(self.cluster_output_dir, "results", design_name, "cluster_design.final.pl"),
            os.path.join(self.cluster_output_dir, "results", design_name, f"{design_name}.gp.pl"),
            os.path.join(self.cluster_output_dir, "results", design_name, f"{design_name}.final.pl"),
            os.path.join(self.cluster_output_dir, "results", f"{design_name}.gp.pl"),
            os.path.join(self.cluster_output_dir, f"{design_name}.gp.pl"),
        ]
        
        cluster_pl_file = None
        for gp_file in possible_gp_files:
            if os.path.exists(gp_file):
                cluster_pl_file = gp_file
                print(f"  Found GP output: {gp_file}")
                break
        
        if cluster_pl_file is None:
            cluster_pl_file = files['pl']
            print(f"  No GP output found, using initial placement: {cluster_pl_file}")
        
        self._builder = builder
        
        return cluster_pl_file
    
    def generate_initial_placement(self,
                                    cluster_pl_file: str,
                                    base_seed: Optional[int] = None,
                                    utilization: float = 0.8,
                                    place_density_lb_addon: Optional[float] = None,
                                    sigma_ratio: float = 0.9,
                                    scatter_mode: str = "gaussian_circle") -> Tuple[str, str]:
        """
        从cluster placement生成初始单元placement
        
        【关键修改】:
        - fixed节点不参与随机撒点
        - movable_init.pl 只包含 movable 节点
        - design.pl 只包含 fixed 节点
        """
        print("\n" + "=" * 70)
        print("Phase 2: Generate Initial Node Placement")
        print("=" * 70)
        # --- random seed control (default uses cluster_random_seed) ---
        if base_seed is None:
            base_seed = int(self.cluster_random_seed) if self.cluster_random_seed is not None else 42
        else:
            base_seed = int(base_seed)

        
        cluster_size_json = os.path.join(self.cluster_output_dir, "cluster_node_sizes.json")
        util_used = getattr(self, "_cluster_utilization_used", None)
        if util_used is None:
            # 如果用户只调用了 generate_initial_placement 而没跑 generator.generate_cluster_nodes，
            # 那就用同样的 lb+addon 公式现算一遍（需要 self._builder 已经存在）
            if place_density_lb_addon is not None and hasattr(self, "_builder") and self._builder is not None:
                subcluster_areas = getattr(self._builder, "subcluster_areas", [])
                placeable_area = float(self.chip_width) * float(self.chip_height)
                total_cluster_area = float(sum(subcluster_areas)) if subcluster_areas is not None else 0.0
                lb = (total_cluster_area / placeable_area) if placeable_area > 0 else 0.0
                lb = max(0.0, min(1.0, lb))
                addon = float(place_density_lb_addon)
                util_used = lb + ((1.0 - lb) * addon) + 0.01
                if util_used > 1.0:
                    raise ValueError(f"Place density exceeds 1.0 (addon={addon}), util={util_used}, lb={lb}")
            else:
                util_used = utilization

        util_used = float(util_used) if util_used is not None else float(utilization)
        # 读取cluster位置（传入fixed_nodes）
        converter = ClusterToNodePlacement(
            hypergraph_builder=self._builder,
            chip_width=self.chip_width,
            chip_height=self.chip_height,
            utilization=util_used,
            sigma_ratio=sigma_ratio,
            fixed_nodes=self.fixed_nodes,  # 【新增】
            cluster_node_size_file=cluster_size_json,   # 【新增】
            scatter_mode=scatter_mode,
        )
        
        cluster_positions = converter.read_cluster_placement(cluster_pl_file)
        # 【新增】cluster_design.final.pl 的“方块”可视化
        plot_cluster_boxes(
            cluster_positions=cluster_positions,
            cluster_boxes=converter.cluster_boxes,
            fixed_nodes=self.fixed_nodes,
            chip_width=self.chip_width,
            chip_height=self.chip_height,
            out_png=os.path.join(self.final_output_dir, "cluster_boxes.png"),
            show=False,
        )
        print(f"  Read {len(cluster_positions)} cluster positions")
        
        # 生成movable节点的placement（fixed节点不参与）
        node_positions = converter.generate_full_placement(
            cluster_positions=cluster_positions,
            base_seed=base_seed
        )
        print(f"  Generated {len(node_positions)} movable node positions")
        # node_positions 生成后立刻可视化
        plot_cluster_scatter(
            node_positions=node_positions,
            builder=self._builder,
            node_names=self.node_names,
            fixed_nodes=self.fixed_nodes,
            chip_width=self.chip_width,
            chip_height=self.chip_height,
            color_by="subcluster",  # 同一个 cluster_* 同色（最符合“cluster-level placement 后撒点”的语义）
            out_png=os.path.join(self.final_output_dir, "init_scatter_subcluster.png"),
            show=False
        )
        # 写入可移动节点文件
        movable_init_file = os.path.join(self.final_output_dir, "movable_init.pl")
        converter.write_placement_file(
            positions=node_positions,
            node_names=self.node_names,
            output_file=movable_init_file
        )
        
        # 写入固定节点文件
        fixed_pl_file = os.path.join(self.final_output_dir, "design.pl")
        converter.write_fixed_placement_file(output_file=fixed_pl_file)
        
        return movable_init_file, fixed_pl_file
    
    def prepare_final_placement(self,
                                 movable_init_file: str,
                                 fixed_pl_file: str,
                                 wts_file: Optional[str] = None,
                                 gpu: int = 0,
                                 iteration: int = 2000,
                                 final_random_seed: Optional[int] = None,
                                 learning_rate: float = 0.01,
                                 net_weight_anneal_iters: int = 0,
                                 run_global_place: bool = True,
                                 use_init_placement_file: bool = True,
                                 max_fanout: Optional[int] = None) -> Dict[str, str]:
        """准备最终placement的输入文件"""
        print("\n" + "=" * 70)
        print("Phase 3: Prepare Final Placement Input")
        print("=" * 70)
        
        # 复制benchmark文件
        print("\n[3.1] Copying benchmark files...")
        files_to_copy = ['.nodes', '.nets', '.scl', '.lib']
        sidecar_files_to_copy = {
            'design.clk',
            'design.timing',
            'design.clock_nets',
            'design.metadata.json',
        }
        def _filter_nets_by_max_fanout(src_nets: str, dst_nets: str, max_fanout: int) -> Tuple[int, int]:
            """
            读取 src_nets，过滤掉 pin 数(=fanout) > max_fanout 的 net，写入 dst_nets。
            返回 (removed_cnt, kept_cnt)。
            支持格式：
            net <name> <numPins>
                inst pin
            endnet
            """
            removed = 0
            kept = 0

            with open(src_nets, "r") as fin, open(dst_nets, "w") as fout:
                in_net = False
                net_name = None
                pin_lines = []
                header_raw = None

                def flush_one():
                    nonlocal removed, kept, net_name, pin_lines, header_raw
                    if net_name is None:
                        return
                    fanout = len(pin_lines)
                    if fanout < 2:
                        # 跟原逻辑一致：少于2端点的 net 没意义（这里选择直接丢弃）
                        removed += 1
                        return
                    if max_fanout > 0 and fanout > max_fanout:
                        removed += 1
                        return

                    # 写出：header 的 pin 数按实际重算，避免源文件不一致
                    fout.write(f"net {net_name} {fanout}\n")
                    for pl in pin_lines:
                        fout.write(pl)
                    fout.write("endnet\n")
                    kept += 1

                for line in fin:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        # 原样透传注释/空行（不在 net block 内）
                        if not in_net:
                            fout.write(line)
                        continue

                    if s.startswith("net "):
                        # flush 上一个（如果格式异常）
                        if in_net:
                            flush_one()

                        parts = s.split()
                        net_name = parts[1] if len(parts) >= 2 else f"net_{kept + removed}"
                        header_raw = line
                        pin_lines = []
                        in_net = True
                        continue

                    if s == "endnet":
                        if in_net:
                            flush_one()
                        in_net = False
                        net_name = None
                        header_raw = None
                        pin_lines = []
                        continue

                    # net 内 pin 行：保持原样（含缩进）
                    if in_net:
                        pin_lines.append(line)
                    else:
                        # 容错：不在 net 内却出现 pin 行，原样写出
                        fout.write(line)

                # 文件结束，若还在 net 内，flush 一次
                if in_net:
                    flush_one()

            return removed, kept
        # 复制benchmark文件
        print("\n[3.1] Copying benchmark files...")
        files_to_copy = ['.nodes', '.nets', '.scl', '.lib']

        filtered_nets_removed = 0
        filtered_nets_kept = 0

        for f in os.listdir(self.benchmark_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in files_to_copy or f in sidecar_files_to_copy:
                src = os.path.join(self.benchmark_dir, f)
                dst = os.path.join(self.final_output_dir, f)

                # ✅ 对 .nets 做 max_fanout 过滤（替代 copy2）
                if ext == ".nets" and max_fanout is not None and int(max_fanout) > 0:
                    removed, kept = _filter_nets_by_max_fanout(src, dst, int(max_fanout))
                    filtered_nets_removed += removed
                    filtered_nets_kept += kept
                    print(f"  Copied+Filtered: {f}  (kept={kept}, removed={removed}, max_fanout={int(max_fanout)})")
                else:
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        print(f"  Copied: {f}")

        # ✅ 统一打印过滤统计
        if max_fanout is not None and int(max_fanout) > 0:
            print(f"[Final Nets] max_fanout={int(max_fanout)} => filtered_out={filtered_nets_removed}, kept={filtered_nets_kept}")
        
        # 复制.wts文件
        print("\n[3.2] Setting up net weights...")
        final_wts = None
        if wts_file and os.path.exists(wts_file):
            final_wts = os.path.join(self.final_output_dir, os.path.basename(wts_file))
            shutil.copy2(wts_file, final_wts)
            print(f"  Net weights: {os.path.basename(wts_file)}")
        else:
            print("  No net weights file")
        print(ClusterPlacementIntegration.prepare_final_placement.__code__.co_filename)
        # 生成.aux文件
        print("\n[3.3] Generating .aux file...")
        aux_files = []
        for f in os.listdir(self.final_output_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.nodes', '.nets', '.wts', '.scl', '.lib']:
                aux_files.append(f)
        
        aux_files.append('design.pl')
        
        _order = {
            '.nodes': 0, '.nets': 1, '.wts': 2, '.pl': 3, '.scl': 4, '.lib': 5
        }
        def _aux_sort_key(name: str):
            ext = os.path.splitext(name)[1].lower()
            return (_order.get(ext, 99), name)
        aux_files = sorted(dict.fromkeys(aux_files), key=_aux_sort_key)
        
        aux_file = os.path.join(self.final_output_dir, "design.aux")
        with open(aux_file, 'w') as f:
            f.write(f"design : {' '.join(aux_files)}\n")
        print(f"  Aux file: design.aux")
        print(f"  Contents: {' '.join(aux_files)}")
        
        # 生成config文件
        print("\n[3.4] Generating DREAMPlaceFPGA config...")
        
        # --- random seed control (default uses cluster_random_seed) ---
        if final_random_seed is not None:
            seed_used = int(final_random_seed)
        elif self.cluster_random_seed is not None:
            seed_used = int(self.cluster_random_seed)
        else:
            seed_used = 1000

        config = {
            "aux_input": aux_file,
            "gpu": gpu,
            "num_threads": 8,
            "num_bins_x": 512,
            "num_bins_y": 512,
            "global_place_stages": [
                {
                    "num_bins_x": 512,
                    "num_bins_y": 512,
                    "iteration": iteration,
                    "learning_rate": learning_rate,
                    "wirelength": "weighted_average",
                    "optimizer": "nesterov"
                }
            ],
            "result_dir": "results",
            "routability_opt_flag": 0,
            "target_density": 1.0,
            "density_weight": 0.01,
            "random_seed": int(seed_used),
            "scale_factor": 1.0,
            "legalize_flag": 0,
            "detailed_place_flag": 0,
            "dtype": "float32",
            "gamma":0.8, 
            "deterministic_flag": 1
        }
        if net_weight_anneal_iters and int(net_weight_anneal_iters) > 0:
            config["global_place_stages"][0]["net_weight_anneal_iters"] = int(net_weight_anneal_iters)
        if use_init_placement_file and run_global_place:
            config["global_place_flag"] = 1
            #config["init_placement_file"] = movable_init_file
            config["global_place_sol"] = ""
            config["place_sol"] = ""
            config["random_center_init_flag"] = 0
            mode_desc = "Mode 1: init_placement_file + Global Placement"
        elif not run_global_place:
            config["global_place_flag"] = 0
            config["init_placement_file"] = ""
            config["global_place_sol"] = movable_init_file
            config["place_sol"] = movable_init_file
            config["random_center_init_flag"] = 1
            mode_desc = "Mode 2: Skip GP, direct Legalization"
        else:
            config["global_place_flag"] = 1
            config["init_placement_file"] = ""
            config["global_place_sol"] = movable_init_file
            config["place_sol"] = movable_init_file
            config["random_center_init_flag"] = 1
            mode_desc = "Mode 3: global_place_sol + Global Placement"
        
        config_file = os.path.join(self.final_output_dir, "dreamplace_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"  Config file: dreamplace_config.json")
        print(f"  {mode_desc}")
        
        output_files = {
            'aux': aux_file,
            'fixed_pl': fixed_pl_file,
            'movable_init': movable_init_file,
            'wts': final_wts,
            'config': config_file,
            'output_dir': self.final_output_dir
        }
        
        return output_files
    
    def run_complete_flow(self,
                          cluster_layouts: Dict,
                          clustering_results: Dict,
                          wts_file: Optional[str] = None,
                          dreamplace_path: str = None,
                          gpu: int = 0,
                          utilization: float = 0.8,
                          sigma_ratio: float = 0.9,
                          cluster_iteration: int = 1000,
                          final_iteration: int = 2000,
                          learning_rate: float = 0.01,
                          run_global_place: bool = True,
                          max_fanout: Optional[int] = None,
                          use_init_placement_file: bool = True) -> Dict[str, str]:
        """运行完整流程"""
        print("\n" + "=" * 70)
        print("Complete Cluster-Based Placement Flow")
        print("=" * 70)
        
        # 解析benchmark
        print("\n[Step 0] Parsing benchmark...")
        self.parse_benchmark()
        
        # Phase 1: Cluster placement
        cluster_pl = self.run_cluster_placement(
            cluster_layouts=cluster_layouts,
            clustering_results=clustering_results,
            dreamplace_path=dreamplace_path,
            gpu=gpu,
            place_density_lb_addon=args.place_density_lb_addon,
            utilization=utilization,
            iteration=cluster_iteration,
            max_fanout=max_fanout
        )
        
        # Phase 2: Generate initial placement
        movable_init_file, fixed_pl_file = self.generate_initial_placement(
            cluster_pl_file=cluster_pl,
            utilization=utilization,
            sigma_ratio=sigma_ratio
        )
        
        # Phase 3: Prepare final placement
        output_files = self.prepare_final_placement(
            movable_init_file=movable_init_file,
            fixed_pl_file=fixed_pl_file,
            wts_file=wts_file,
            gpu=gpu,
            iteration=final_iteration,
            learning_rate=learning_rate,
            run_global_place=run_global_place,
            use_init_placement_file=use_init_placement_file,
            max_fanout=max_fanout
        )
        
        # 打印总结
        print("\n" + "=" * 70)
        print("Flow Completed!")
        print("=" * 70)
        print("\n[Generated Files]")
        for key, path in output_files.items():
            if path:
                print(f"  {key}: {path}")
        
        print("\n[File Organization]")
        print(f"  design.pl: Fixed nodes only ({len(self.fixed_nodes)} nodes with FIXED marker)")
        print(f"  movable_init.pl: Movable nodes initial positions (integer coordinates)")
        
        print("\n[Fixed Nodes Handling]")
        print(f"  - Cluster-level .nodes: includes fixed nodes with original types")
        print(f"  - Cluster-level .pl: includes fixed nodes with original positions (FIXED)")
        print(f"  - Cluster scatter: fixed nodes NOT participating in random placement")
        
        print("\n[Next Step: Run Final Placement]")
        print(f"  python dreamplacefpga/Placer.py {output_files['config']}")
        
        return output_files


# =============================================================================
# Part 6: 与现有Pipeline集成
# =============================================================================

def integrate_with_main_pipeline(
    pipeline,
    output_dir: str,
    wts_file: Optional[str] = None,
    dreamplace_path: str = None,
    gpu: int = 0,
    cluster_iteration: int = 1000,
    final_iteration: int = 2000,
    utilization: float = 0.8,
    sigma_ratio: float = 0.9,
    max_fanout: Optional[int] = None,   # 新增：pipeline 入口透传
) -> Dict[str, str]:
    """与main_pipeline_with_viz.py中的EnhancedFPGAPipeline集成"""
    integrator = ClusterPlacementIntegration(
        benchmark_dir=pipeline.benchmark_dir,
        output_dir=output_dir
    )
    
    return integrator.run_complete_flow(
        cluster_layouts=pipeline.cluster_layouts,
        clustering_results=pipeline.clustering_results,
        wts_file=wts_file,
        dreamplace_path=dreamplace_path,
        gpu=gpu,
        utilization=utilization,
        sigma_ratio=sigma_ratio,
        cluster_iteration=cluster_iteration,
        final_iteration=final_iteration,
        max_fanout=max_fanout,           # 新增：透传到完整 flow
    )


# =============================================================================
# Main Entry
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Cluster-Level Placement Integration (with Fixed Nodes Support)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
流程说明:
  1. 从clustering结果构建cluster级别超图（fixed节点不参与clustering）
  2. 生成cluster-level benchmark:
     - .nodes: cluster虚拟节点 + fixed节点
     - .pl: cluster随机位置 + fixed节点原始位置(FIXED标记)
  3. 运行DREAMPlaceFPGA进行cluster-level global placement
  4. 在每个cluster内分配单元位置（fixed节点不参与随机撒点）
  5. 生成初始placement:
     - movable_init.pl: 可移动节点位置
     - design.pl: 固定节点位置(FIXED标记)

示例:
  python cluster_placement_integration_fixed.py \\
      --benchmark_dir benchmarks/design1 \\
      --cluster_layouts cluster_layouts.json \\
      --clustering_results clustering_results.json \\
      --output_dir output \\
      --dreamplace_path /path/to/DREAMPlaceFPGA
        """
    )
    
    parser.add_argument('--benchmark_dir', type=str, required=True,
                       help='FPGA benchmark目录')
    parser.add_argument('--cluster_layouts', type=str, required=True,
                       help='cluster_layouts JSON文件')
    parser.add_argument('--clustering_results', type=str, default=None,
                       help='clustering_results JSON文件')
    parser.add_argument('--wts_file', type=str, default=None,
                       help='.wts权重文件')
    parser.add_argument('--output_dir', type=str, default='./output',
                       help='输出目录')
    parser.add_argument('--dreamplace_path', type=str, default=None,
                       help='DREAMPlaceFPGA路径')
    
    parser.add_argument('--gpu', type=int, default=0,
                       help='是否使用GPU')
    parser.add_argument('--place_density_lb_addon', type=float, default=None,
                        help='PLACE_DENSITY_LB_ADDON in [0,0.99]. '
                            'Final util = lb + (1-lb)*addon + 0.01, where lb = sum(cluster_area)/placeable_area')

    parser.add_argument('--utilization', type=float, default=0.8,
                       help='cluster node utilization (0,1]; inflate area by /utilization for cluster_node_sizes and scatter')
    parser.add_argument('--sigma_ratio', type=float, default=0.9,
                        help='random scatter sigma ratio inside each cluster (sigma = R * sigma_ratio)')
    parser.add_argument('--cluster_iteration', type=int, default=1000,
                       help='Cluster placement迭代次数')
    parser.add_argument('--final_iteration', type=int, default=2000,
                       help='Final placement迭代次数')
    parser.add_argument('--learning_rate', type=float, default=0.01,
                       help='学习率')
    parser.add_argument('--max_fanout', type=int, default=0,
                    help='cluster-level placement阶段过滤高扇出net；0/负数表示关闭')
    args = parser.parse_args()
    
    # 加载clustering结果
    with open(args.cluster_layouts, 'r') as f:
        cluster_layouts_raw = json.load(f)
    
    cluster_layouts = {}
    for k, v in cluster_layouts_raw.items():
        cluster_layouts[int(k)] = {
            'node_indices': v['node_indices'],
            'positions': np.array(v.get('positions', []))
        }
    
    clustering_results = None
    if args.clustering_results:
        with open(args.clustering_results, 'r') as f:
            clustering_results_raw = json.load(f)
        clustering_results = {int(k): v for k, v in clustering_results_raw.items()}
    else:
        clustering_results = {}
    
    # 运行
    integrator = ClusterPlacementIntegration(
        benchmark_dir=args.benchmark_dir,
        output_dir=args.output_dir
    )
    
    output_files = integrator.run_complete_flow(
        cluster_layouts=cluster_layouts,
        clustering_results=clustering_results,
        wts_file=args.wts_file,
        dreamplace_path=args.dreamplace_path,
        gpu=args.gpu,
        utilization=args.utilization,
        sigma_ratio=args.sigma_ratio,
        cluster_iteration=args.cluster_iteration,
        final_iteration=args.final_iteration,
        max_fanout=(None if args.max_fanout <= 0 else args.max_fanout),
        learning_rate=args.learning_rate
    )


if __name__ == "__main__":
    main()
