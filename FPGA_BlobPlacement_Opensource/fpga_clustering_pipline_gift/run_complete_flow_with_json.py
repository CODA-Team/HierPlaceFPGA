#!/usr/bin/env python3
# 在任何其他 import 之前固定 hash seed，消除 set/dict 顺序的跨运行随机性
import os as _os
if "PYTHONHASHSEED" not in _os.environ:
    _os.environ["PYTHONHASHSEED"] = "0"
"""
Complete FPGA Placement Flow with Clustering (Enhanced Version)
================================================================

完整流程:
1. Louvain聚类 + GIFT布局 + SpecPart sub-clustering
2. Cluster-level global placement (将sub-clusters作为节点)
3. 在每个cluster内分配单元位置，生成初始布局
4. Net reweighting (基于clustering结果调整网络权重)
5. 输出最终的DREAMPlaceFPGA输入文件

新增功能:
- --skip_clustering: 跳过聚类阶段，从已有的聚类结果开始
- 独立保存 cluster-level 和 final placement 的 DREAMPlace 日志

用法:
    # 完整流程
    python run_complete_flow.py --benchmark_dir benchmarks/design1 --output_dir output
    
    # 指定DREAMPlaceFPGA路径以运行cluster placement
    python run_complete_flow.py --benchmark_dir benchmarks/design1 \\
        --dreamplace_path /path/to/DREAMPlaceFPGA --output_dir output
    
    # 从cluster placement开始（跳过聚类）
    python run_complete_flow_enhanced.py --benchmark_dir benchmarks/design1 \\
        --dreamplace_path /path/to/DREAMPlaceFPGA --output_dir output --skip_clustering

Author: Complete Flow Integration (Enhanced)
"""

import os
import sys
import json
import argparse
import time
import re
import numpy as np
from typing import Dict, Optional, Any
import subprocess
import shutil
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))


def _resolve_project_path(path: Optional[str]) -> Optional[str]:
    """Resolve package-relative paths after the project is moved."""
    if path is None or os.path.isabs(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(PROJECT_ROOT, path))


class _TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self.streams:
            s.flush()

    def isatty(self):
        return any(getattr(s, "isatty", lambda: False)() for s in self.streams)


def _enable_terminal_logging(output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "terminal_output.log")
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)

    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.__stdout__, log_file)
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.__stderr__, log_file)

    return log_path


_OVERFLOW_LINE_RE = re.compile(r"iter:\s*(\d+).*?Overflow\s*\[([^\]]+)\]")
_TARGET_OVERFLOW_RE = re.compile(r"targetOverflow=\[([^\]]+)\]")


def _parse_float_vector(text: str):
    return [float(x) for x in re.split(r"[\s,]+", text.strip()) if x]


def _report_dreamplace_convergence(log_file: str, label: str) -> None:
    """Report whether DREAMPlaceFPGA stopped by target overflow or iteration budget."""
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


_DPFPGA_CELL_ALIASES = {
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


def _dreamplace_cell_alias(cell_type: str) -> str:
    return _DPFPGA_CELL_ALIASES.get(cell_type, cell_type)


def _dreamplace_site_alias(site_type: str) -> str:
    if site_type == "PLB":
        return "SLICE"
    if site_type in {"RAMA", "RAMB"}:
        return "BRAM"
    if site_type in {"IOA", "IOB", "GCLK", "IPPIN"}:
        return "IO"
    return site_type


def _parse_fixed_nodes_from_pl(pl_path: str) -> set:
    fixed = set()
    if not pl_path or not os.path.exists(pl_path):
        return fixed
    with open(pl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            if any(tok.upper().strip("/") == "FIXED" for tok in parts[3:]):
                fixed.add(parts[0])
    return fixed


def _write_dreamplace_compat_nodes(src: str, dst: str, fixed_nodes: set) -> dict:
    stats = {"nodes": 0, "fixed_as_ibuf": 0, "aliased": 0}
    with open(src, "r", encoding="utf-8", errors="ignore") as rf, \
            open(dst, "w", encoding="utf-8") as wf:
        for line in rf:
            parts = line.split()
            if len(parts) < 2 or parts[0].startswith("#"):
                wf.write(line)
                continue
            name, raw_type = parts[0], parts[1]
            if name in fixed_nodes:
                compat_type = "IBUF"
                stats["fixed_as_ibuf"] += 1
            else:
                compat_type = _dreamplace_cell_alias(raw_type)
            if compat_type != raw_type:
                stats["aliased"] += 1
            wf.write(f"{name} {compat_type}\n")
            stats["nodes"] += 1
    return stats


def _write_dreamplace_compat_nets(src: str, dst: str, fixed_nodes: set) -> dict:
    stats = {"nets": 0, "fixed_pin_rewrites": 0}
    with open(src, "r", encoding="utf-8", errors="ignore") as rf, \
            open(dst, "w", encoding="utf-8") as wf:
        in_net = False
        for line in rf:
            parts = line.split()
            if not parts:
                wf.write(line)
                continue
            if parts[0] == "net":
                in_net = True
                stats["nets"] += 1
                wf.write(line)
            elif parts[0] == "endnet":
                in_net = False
                wf.write(line)
            elif in_net and len(parts) >= 2 and parts[0] in fixed_nodes:
                wf.write(f"  {parts[0]} I_0\n")
                stats["fixed_pin_rewrites"] += 1
            else:
                wf.write(line)
    return stats


def _write_dreamplace_compat_scl(src: str, dst: str) -> dict:
    stats = {"sitemap_entries": 0, "aliased_sites": 0}
    with open(src, "r", encoding="utf-8", errors="ignore") as rf:
        raw_lines = rf.readlines()

    width = height = None
    sitemap_rows = []
    in_sitemap = False
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("SITEMAP"):
            parts = stripped.split()
            if len(parts) >= 3:
                width, height = parts[1], parts[2]
            in_sitemap = True
            continue
        if in_sitemap:
            parts = stripped.split()
            if len(parts) >= 3:
                raw_site = parts[2]
                site = _dreamplace_site_alias(raw_site)
                if site != raw_site:
                    stats["aliased_sites"] += 1
                sitemap_rows.append((parts[0], parts[1], site))
                stats["sitemap_entries"] += 1

    if width is None or height is None:
        width, height = "1", "1"

    with open(dst, "w", encoding="utf-8") as wf:
        wf.write("# DREAMPlaceFPGA compatibility view of final input; real 4_final_input is unchanged.\n")
        wf.write("SITE SLICE\n  LUT 16\n  FF 16\n  CARRY8 1\nEND SITE\n\n")
        wf.write("SITE DSP\n  DSP48E2 1\nEND SITE\n\n")
        wf.write("SITE BRAM\n  RAMB36E2 1\nEND SITE\n\n")
        wf.write("SITE IO\n  IO 64\nEND SITE\n\n")
        wf.write("RESOURCES\n")
        wf.write("  LUT LUT1 LUT2 LUT3 LUT4 LUT5 LUT6\n")
        wf.write("  FF FDRE\n")
        wf.write("  CARRY8 CARRY8\n")
        wf.write("  DSP48E2 DSP48E2\n")
        wf.write("  RAMB36E2 RAMB36E2\n")
        wf.write("  IO IBUF OBUF BUFGCE\n")
        wf.write("END RESOURCES\n\n")
        wf.write(f"SITEMAP {width} {height}\n")
        for x, y, site in sitemap_rows:
            wf.write(f"{x} {y} {site}\n")
        wf.write("END SITEMAP\n")
    return stats


def _write_dreamplace_compat_lib(src: str, dst: str) -> dict:
    cells = {}
    aliases = {}
    current_cell = None
    current_pins = []

    def flush_cell():
        nonlocal current_cell, current_pins
        if current_cell is None:
            return
        alias = _dreamplace_cell_alias(current_cell)
        aliases[current_cell] = alias
        pin_map = cells.setdefault(alias, {})
        for pin_line in current_pins:
            parts = pin_line.split()
            if len(parts) >= 2:
                direction = "OUTPUT" if len(parts) >= 3 and parts[2].upper() == "OUTPUT" else "INPUT"
                # The DREAMPlaceFPGA Bookshelf grammar is strict for .lib pin lines;
                # drop public_release attributes such as CLOCK/CTRL in the compat view.
                pin_map.setdefault(parts[1], f"PIN {parts[1]} {direction}")
        current_cell = None
        current_pins = []

    with open(src, "r", encoding="utf-8", errors="ignore") as rf:
        for raw in rf:
            stripped = raw.strip()
            if stripped.startswith("CELL "):
                flush_cell()
                parts = stripped.split()
                current_cell = parts[1] if len(parts) >= 2 else None
                current_pins = []
            elif stripped.startswith("END CELL"):
                flush_cell()
            elif current_cell is not None and stripped.startswith("PIN "):
                current_pins.append(stripped)
        flush_cell()

    cells.setdefault("IBUF", {}).setdefault("I_0", "PIN I_0 INPUT")
    cells.setdefault("IBUF", {}).setdefault("O_0", "PIN O_0 OUTPUT")

    with open(dst, "w", encoding="utf-8") as wf:
        for cell in sorted(cells):
            wf.write(f"CELL {cell}\n")
            for pin in sorted(cells[cell]):
                wf.write(f"  {cells[cell][pin]}\n")
            wf.write("END CELL\n\n")

    changed_aliases = {k: v for k, v in aliases.items() if k != v}
    return {"cells": len(cells), "aliases": changed_aliases}


def _prepare_dreamplace_compat_final_input(final_output: str, config: dict) -> tuple:
    """Create a sibling DREAMPlaceFPGA-only view without mutating real 4_final_input."""
    final_output = os.path.abspath(final_output)
    compat_dir = final_output.rstrip(os.sep) + "_dreamplace_compat"
    os.makedirs(compat_dir, exist_ok=True)

    fixed_nodes = _parse_fixed_nodes_from_pl(os.path.join(final_output, "design.pl"))
    stats = {"fixed_nodes": len(fixed_nodes)}

    passthrough = {
        "design.pl",
        "movable_init.pl",
        "design.weights",
        "design.wts",
        "design.regions",
        "design.cascade_shape",
        "design.macros",
        "design.clk",
        "design.timing",
        "design.clock_nets",
        "design.metadata.json",
    }
    for name in passthrough:
        src = os.path.join(final_output, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(compat_dir, name))

    stats["nodes"] = _write_dreamplace_compat_nodes(
        os.path.join(final_output, "design.nodes"),
        os.path.join(compat_dir, "design.nodes"),
        fixed_nodes,
    )
    stats["nets"] = _write_dreamplace_compat_nets(
        os.path.join(final_output, "design.nets"),
        os.path.join(compat_dir, "design.nets"),
        fixed_nodes,
    )
    stats["scl"] = _write_dreamplace_compat_scl(
        os.path.join(final_output, "design.scl"),
        os.path.join(compat_dir, "design.scl"),
    )
    stats["lib"] = _write_dreamplace_compat_lib(
        os.path.join(final_output, "design.lib"),
        os.path.join(compat_dir, "design.lib"),
    )

    aux_path = os.path.join(compat_dir, "design.aux")
    with open(aux_path, "w", encoding="utf-8") as f:
        f.write("design : design.nodes design.nets design.wts design.pl design.scl design.lib\n")

    compat_config = dict(config)
    compat_config["aux_input"] = aux_path
    compat_config["init_placement_file"] = os.path.join(compat_dir, "movable_init.pl")
    weights_path = os.path.join(compat_dir, "design.weights")
    compat_config["net_weight_file"] = weights_path if os.path.exists(weights_path) else ""
    compat_config["result_dir"] = "results"
    compat_config_path = os.path.join(compat_dir, "dreamplace_config.json")
    with open(compat_config_path, "w", encoding="utf-8") as f:
        json.dump(compat_config, f, indent=2)

    stats_path = os.path.join(compat_dir, "compat_summary.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    return compat_dir, compat_config_path, stats_path

# 确保能导入其他模块
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)


def load_existing_clustering(clustering_output: str):
    """
    从已有的聚类结果加载数据
    
    Returns:
        tuple: (cluster_layouts, clustering_results)
    """
    layouts_file = os.path.join(clustering_output, "cluster_layouts.json")
    results_file = os.path.join(clustering_output, "clustering_results.json")
    
    if not os.path.exists(layouts_file):
        raise FileNotFoundError(f"Cluster layouts file not found: {layouts_file}")
    
    # 加载 cluster_layouts
    with open(layouts_file, 'r') as f:
        cluster_layouts_raw = json.load(f)
    
    cluster_layouts = {}
    for k, v in cluster_layouts_raw.items():
        entry = {
            'node_indices': v['node_indices'],
            'positions': np.array(v.get('positions', []))
        }
        if v.get('locked'):
            entry['locked'] = True
            entry['lock_type'] = v.get('lock_type', '')
        cluster_layouts[int(k)] = entry
    
    # 加载 clustering_results
    clustering_results = {}
    if os.path.exists(results_file):
        with open(results_file, 'r') as f:
            clustering_results_raw = json.load(f)
        clustering_results = {int(k): v for k, v in clustering_results_raw.items()}
    
    print(f"  Loaded {len(cluster_layouts)} clusters from {layouts_file}")
    print(f"  Loaded clustering results from {results_file}")
    
    return cluster_layouts, clustering_results


def _run_density_gate_analysis(
    benchmark_dir: str,
    clustering_output: str,
    max_net_fanout: int
) -> Dict[str, Any]:
    """
    运行 cluster/subcluster 超图密度分析，用于 net reweighting 门控。

    Returns:
        {
            "success": bool,
            "cluster_weighted_mean_density": float|None,
            "subcluster_weighted_mean_density": float|None,
            "density_sum": float|None,
            "max_net_fanout": int,
            "error": str|None,
            ...
        }
    """
    info: Dict[str, Any] = {
        "success": False,
        "cluster_weighted_mean_density": None,
        "subcluster_weighted_mean_density": None,
        "density_sum": None,
        "max_net_fanout": int(max_net_fanout),
        "error": None,
    }
    try:
        from cluster_conductance_analysis import (
            BookshelfParser,
            ClusteringInfo,
            HypergraphDensityAnalyzer,
        )

        parser = BookshelfParser(benchmark_dir)
        clustering = ClusteringInfo(
            clustering_output,
            fixed_node_indices=parser.fixed_node_indices(),
        )
        analyzer = HypergraphDensityAnalyzer(
            parser,
            clustering,
            max_net_fanout=int(max_net_fanout),
        )
        report = analyzer.generate_report()

        cluster_agg = report.get("cluster_aggregate", {})
        subcluster_agg = report.get("subcluster_aggregate", {})
        cluster_density = float(cluster_agg.get("weighted_mean_net_density", 0.0))
        subcluster_density = float(subcluster_agg.get("weighted_mean_net_density", 0.0))
        density_sum = cluster_density + subcluster_density

        info.update({
            "success": True,
            "cluster_weighted_mean_density": cluster_density,
            "subcluster_weighted_mean_density": subcluster_density,
            "density_sum": density_sum,
            "method": report.get("method", {}).get("name"),
            "subcluster_net_source": report.get("subcluster_summary", {}).get("subcluster_net_source"),
        })
    except Exception as e:
        info["error"] = str(e)

    return info


def run_complete_flow(
    benchmark_dir: str,
    output_base_dir: str,
    aux_file: str = None,
    # Clustering参数
    min_cluster_size: int = 50,
    louvain_resolution: float = 1.0,
    gift_scale: float = 0.5,
    specpart_ub_factor: int = 10,
    num_trees: int = 5,
    best_solns: int = 5,
    max_cluster_size: Optional[int] = None,
    top_k: int = 5,
    cluster_random_seed: int = 42,
    macro_neighbor_depth: int = -1,
    specpart_num_seeds: int = 5,
    specpart_timeout: int = 3600,
    specpart_num_workers: int = 15,
    specpart_per_job_timeout: int = 120,
    # ✅ 新增：cluster nets 权重参数（用于 fixed↔cluster 强拉）
    cluster_base_weight: float = 1,
    cluster_fixed_cluster_weight: float = 10.0,
    # Cluster placement参数
    run_cluster_placement: bool = True,
    cluster_iteration: int = 1000,
    place_density_lb_addon: float = 0.0,
    utilization: float = 0.8,
    sigma_ratio: float = 0.95,
    max_fanout: Optional[int] = None,
    scatter_mode: str = "gaussian_circle",
    # Net reweighting参数
    intra_subcluster_weight: float = 1.5,
    intra_cluster_weight: float = 1.0,
    inter_cluster_weight: float = 0.8,
    density_skip_threshold: float = 1.3,
    # Final placement参数
    net_weight_anneal_iters: int = 0,
    gpu: int = 0,
    final_iteration: int = 2000,
    learning_rate: float = 0.01,
    # ✅ NEW: allow json/cli to control dreamplace config
    density_weight: float = 0.01,
    gamma: float = 0.8,
    routability_opt_flag: int = 1,
    random_seed = 1000,
    node_area_adjust_overflow = 0.1,
    # DREAMPlaceFPGA
    dreamplace_path: str = None,
    # 是否在生成 4_final_input 后直接运行最终 placement
    run_final_placement: bool = False,
    final_dreamplace_compat: bool = False,
    # 可视化
    visualize: bool = False,
    # 新增: 跳过聚类阶段
    skip_clustering: bool = False,
    # 新增: specpart_mode 控制 GIFT 特征使用方式
    # "gift_single": 只用 GIFT 坐标做一次 tree_partition + overlay + optimal_partitioner（无迭代精化）
    # "gift_then_spectral": 第一次迭代用 GIFT，后续迭代用原始 solve_eigs 谱方法
    # "louvain_kway": 不使用 GIFT，直接用 Louvain cluster 并行运行完整 K_SpecPart
    specpart_mode: str = "gift_then_spectral"
):
    """
    运行完整流程
    
    Args:
        benchmark_dir: FPGA benchmark目录
        output_base_dir: 输出基础目录
        aux_file: .aux文件名
        
        # Clustering参数
        min_cluster_size: Louvain最小cluster大小
        louvain_resolution: Louvain分辨率
        gift_scale: GIFT初始位置范围
        specpart_ub_factor: SpecPart不平衡因子
        num_trees: SpecPart树数量
        best_solns: 选择的最佳解数量
        
        # Cluster placement参数
        run_cluster_placement: 是否运行cluster-level placement
        cluster_iteration: cluster placement迭代次数
        
        # Net reweighting参数
        intra_subcluster_weight: 同一sub-cluster内网络权重
        intra_cluster_weight: 同一cluster内跨sub-cluster网络权重
        inter_cluster_weight: 跨cluster网络权重
        density_skip_threshold: 若 cluster/subcluster 加权平均密度和超过该阈值，则强制全1权重
        
        # Final placement参数
        gpu: GPU设置
        final_iteration: 最终placement迭代次数
        learning_rate: 学习率
        
        # DREAMPlaceFPGA
        dreamplace_path: DREAMPlaceFPGA路径
        
        # 可视化
        visualize: 是否生成可视化
        
        # 新增
        skip_clustering: 是否跳过聚类阶段（从已有结果恢复）
    """
    #
    #设置全局随机种子，确保可复现性
    import random
    random.seed(int(cluster_random_seed))
    np.random.seed(int(cluster_random_seed))

    # ✅ DEBUG: 打印所有 seed 参数，方便排查可复现性
    print(f"[DEBUG][Seed] cluster_random_seed={cluster_random_seed}, random_seed={random_seed}")
    print(f"Top-K partitions: {top_k}")
    print("=" * 80)
    print("Complete FPGA Placement Flow with Clustering")
    if skip_clustering:
        print("  [RESUME MODE: Skipping clustering, starting from cluster placement]")
    print("=" * 80)
    print(f"\nBenchmark: {benchmark_dir}")
    print(f"Output: {output_base_dir}")
    print(f"[DEBUG][specpart_mode] specpart_mode={specpart_mode}")
    
    # 创建输出目录
    clustering_output = os.path.join(output_base_dir, "1_clustering")
    cluster_placement_output = os.path.join(output_base_dir, "2_cluster_placement")
    reweighting_output = os.path.join(output_base_dir, "3_net_reweighting")
    final_output = os.path.join(output_base_dir, "4_final_input")
    
    for d in [clustering_output, cluster_placement_output, reweighting_output, final_output]:
        os.makedirs(d, exist_ok=True)
    
    # Timing dict to collect phase durations
    phase_timings = {}
    flow_t0 = time.time()

    # =========================================================================
    # Phase 1: Clustering Pipeline (Louvain + GIFT + SpecPart)
    # =========================================================================
    phase1_t0 = time.time()

    if skip_clustering:
        print("\n" + "=" * 80)
        print("PHASE 1: Loading Existing Clustering Results [SKIP MODE]")
        print("=" * 80)
        
        try:
            cluster_layouts, clustering_results = load_existing_clustering(clustering_output)
            
            # 创建一个简单的 pipeline 对象来保持接口兼容
            class LoadedPipeline:
                def __init__(self, layouts, results, bench_dir):
                    self.cluster_layouts = layouts
                    self.clustering_results = results
                    self.benchmark_dir = bench_dir
            
            pipeline = LoadedPipeline(cluster_layouts, clustering_results, benchmark_dir)
            layouts_file = os.path.join(clustering_output, "cluster_layouts.json")
            results_file = os.path.join(clustering_output, "clustering_results.json")
            
        except FileNotFoundError as e:
            print(f"\nError: Cannot skip clustering - {e}")
            print("Please run the full flow first to generate clustering results.")
            return None
    else:
        print("\n" + "=" * 80)
        print("PHASE 1: Clustering Pipeline (Louvain + GIFT + SpecPart)")
        print("=" * 80)
        
        # 导入模块
        try:
            from main_pipeline_with_viz import EnhancedFPGAPipeline
        except ImportError:
            print("Warning: main_pipeline_with_viz not found, using simplified clustering")
            from fpga_clustering_pipeline_gift import FPGAClusteringPipeline
            
            # 使用基础pipeline
            base_pipeline = FPGAClusteringPipeline(benchmark_dir, clustering_output)
            cluster_layouts = base_pipeline.run_pipeline(
                aux_file=aux_file,
                min_cluster_size=min_cluster_size,
                louvain_resolution=louvain_resolution,
                gift_scale=gift_scale,
                use_mixed_filter=True,
                cluster_random_seed=int(cluster_random_seed),
                max_cluster_size=max_cluster_size,
                macro_neighbor_depth=macro_neighbor_depth,
                max_fanout=max_fanout if max_fanout else 500
            )
            
            # 创建兼容的结构
            class SimplePipeline:
                def __init__(self, base, layouts):
                    self.benchmark_dir = base.benchmark_dir
                    self.cluster_layouts = layouts
                    self.clustering_results = {}
                    self.base_pipeline = base
            
            pipeline = SimplePipeline(base_pipeline, cluster_layouts)

            # Delayed assignment of isolated nodes (no SpecPart in this path)
            if hasattr(base_pipeline, 'isolated_nodes') and base_pipeline.isolated_nodes:
                pipeline.cluster_layouts, pipeline.clustering_results = \
                    base_pipeline.delayed_assign_isolated_nodes(
                        pipeline.cluster_layouts, pipeline.clustering_results)
        else:
            # 使用完整pipeline
            pipeline = EnhancedFPGAPipeline(benchmark_dir, clustering_output, cluster_random_seed=int(cluster_random_seed))
            pipeline.run_full_pipeline(
                aux_file=aux_file,
                min_cluster_size=min_cluster_size,
                louvain_resolution=louvain_resolution,
                gift_scale=gift_scale,
                specpart_ub_factor=specpart_ub_factor,
                num_trees=num_trees,
                best_solns=best_solns,
                visualize_gift=visualize,
                run_specpart_clustering=True,
                max_cluster_size=max_cluster_size,
                macro_neighbor_depth=macro_neighbor_depth,
                specpart_num_seeds=specpart_num_seeds,
                specpart_timeout=specpart_timeout,
                specpart_num_workers=specpart_num_workers,
                specpart_mode=specpart_mode,
                specpart_per_job_timeout=specpart_per_job_timeout,
                max_fanout=max_fanout if max_fanout else 500
            )
        
        if len(pipeline.cluster_layouts) == 0:
            print("\nError: No clusters found!")
            return None
        
        # 如果不需要可视化，删除生成的可视化文件
        if not visualize:
            viz_dir = os.path.join(clustering_output, "visualizations")
            if os.path.exists(viz_dir):
                shutil.rmtree(viz_dir)
                print("  Removed visualizations (--no_viz specified)")
        
        # 保存clustering结果
        cluster_layouts_save = {}
        for k, v in pipeline.cluster_layouts.items():
            entry = {
                'node_indices': [int(i) for i in v['node_indices']],
                'positions': v['positions'].tolist() if isinstance(v['positions'], np.ndarray) else v['positions']
            }
            if v.get('locked'):
                entry['locked'] = True
                entry['lock_type'] = v.get('lock_type', '')
            cluster_layouts_save[k] = entry
        
        layouts_file = os.path.join(clustering_output, "cluster_layouts.json")
        with open(layouts_file, 'w') as f:
            json.dump(cluster_layouts_save, f, indent=2)
        print(f"\n  Saved cluster layouts: {layouts_file}")
        
        clustering_results_save = {}
        if hasattr(pipeline, 'clustering_results'):
            for k, v in pipeline.clustering_results.items():
                entry = {
                    'clusters': [[int(i) for i in c] for c in v.get('clusters', [])],
                    'num_sub_clusters': v.get('num_sub_clusters', 0)
                }
                if v.get('locked'):
                    entry['locked'] = True
                    entry['lock_type'] = v.get('lock_type', '')
                clustering_results_save[k] = entry
        
        results_file = os.path.join(clustering_output, "clustering_results.json")
        with open(results_file, 'w') as f:
            json.dump(clustering_results_save, f, indent=2)
        print(f"  Saved clustering results: {results_file}")

    phase_timings['Phase 1: Clustering'] = time.time() - phase1_t0
    print(f"\n  [Timing] Phase 1 completed in {phase_timings['Phase 1: Clustering']:.1f}s")

    # =========================================================================
    # Phase 2: Cluster-Level Placement
    # =========================================================================
    phase2_t0 = time.time()
    init_pl_file = None
    movable_init_file = None
    fixed_pl_file = None
    
    if run_cluster_placement:
        print("\n" + "=" * 80)
        print("PHASE 2: Cluster-Level Global Placement")
        print("=" * 80)
        
        from cluster_placement_integration import ClusterPlacementIntegration
        
        cluster_integrator = ClusterPlacementIntegration(
            benchmark_dir=benchmark_dir,
            cluster_random_seed=cluster_random_seed,
            output_dir=cluster_placement_output
        )
        
        # 解析benchmark
        cluster_integrator.parse_benchmark()
        
        # 运行cluster placement
        cluster_pl = cluster_integrator.run_cluster_placement(
            cluster_layouts=pipeline.cluster_layouts,
            clustering_results=pipeline.clustering_results if hasattr(pipeline, 'clustering_results') else {},
            dreamplace_path=dreamplace_path,
            gpu=gpu,
            utilization=utilization,
            place_density_lb_addon=place_density_lb_addon,
            max_fanout=max_fanout,
            iteration=cluster_iteration,
             # ✅ 新增：透传到 cluster nets 权重
            base_weight=cluster_base_weight,
            cluster_random_seed=cluster_random_seed,
            fixed_cluster_weight=cluster_fixed_cluster_weight
        )
        
        # 记录 cluster placement 的日志位置
        cluster_log = os.path.join(cluster_placement_output, 'cluster_placement', 'cluster_placement.log')
        if os.path.exists(cluster_log):
            print(f"\n  Cluster placement log: {cluster_log}")
        
        # 生成初始placement - 返回 (movable_init_file, fixed_pl_file) 元组
        movable_init_file, fixed_pl_file = cluster_integrator.generate_initial_placement(
            cluster_pl_file=cluster_pl,
            utilization=utilization,
            place_density_lb_addon=place_density_lb_addon,
            #base_seed=10000,#固定种子进行实验
            base_seed=int(cluster_random_seed),
            sigma_ratio=sigma_ratio,
            scatter_mode=scatter_mode
        )
        
        # 保持兼容性，init_pl_file指向movable_init.pl
        init_pl_file = movable_init_file
        
        print(f"\n  Movable init placement: {movable_init_file}")
        print(f"  Fixed nodes placement: {fixed_pl_file}")

    phase_timings['Phase 2: Cluster Placement'] = time.time() - phase2_t0
    print(f"\n  [Timing] Phase 2 completed in {phase_timings['Phase 2: Cluster Placement']:.1f}s")

    # =========================================================================
    # Phase 3: Net Reweighting
    # =========================================================================
    phase3_t0 = time.time()
    effective_intra_subcluster_weight = float(intra_subcluster_weight)
    effective_intra_cluster_weight = float(intra_cluster_weight)
    effective_inter_cluster_weight = float(inter_cluster_weight)
    density_gate_triggered = False
    density_gate_info: Dict[str, Any] = {}
    density_gate_summary_file = None

    print("\n" + "=" * 80)
    print("PHASE 3: Net Reweighting")
    print("=" * 80)

    analysis_max_fanout = int(max_fanout) if (max_fanout is not None and int(max_fanout) > 0) else 500
    density_gate_info = _run_density_gate_analysis(
        benchmark_dir=benchmark_dir,
        clustering_output=clustering_output,
        max_net_fanout=analysis_max_fanout,
    )

    if density_gate_info.get("success"):
        cluster_density = float(density_gate_info["cluster_weighted_mean_density"])
        subcluster_density = float(density_gate_info["subcluster_weighted_mean_density"])
        density_sum = float(density_gate_info["density_sum"])
        threshold = float(density_skip_threshold)
        density_gate_triggered = density_sum > threshold

        print("\n  [Density Gate] cluster_conductance_analysis completed.")
        print(f"    cluster_weighted_mean_density:    {cluster_density:.6f}")
        print(f"    subcluster_weighted_mean_density: {subcluster_density:.6f}")
        print(f"    density_sum:                      {density_sum:.6f}")
        print(f"    density_skip_threshold:           {threshold:.6f}")
        print(f"    analysis_max_net_fanout:          {analysis_max_fanout}")
        print(f"    decision: {'force_all_ones' if density_gate_triggered else 'use_original_weights'}")
    else:
        density_gate_triggered = True
        print("\n  [Density Gate] Warning: density analysis failed.")
        print(f"    error: {density_gate_info.get('error')}")
        print("    fallback decision: force_all_ones")

    if density_gate_triggered:
        effective_intra_subcluster_weight = 1.0
        effective_intra_cluster_weight = 1.0
        effective_inter_cluster_weight = 1.0
        print("  [Density Gate] Applying uniform net weights (=1.0) for all net classes.")
    else:
        print("  [Density Gate] Keep user-provided net reweighting parameters.")

    density_gate_summary = {
        "analysis_success": bool(density_gate_info.get("success")),
        "analysis_error": density_gate_info.get("error"),
        "analysis_max_net_fanout": analysis_max_fanout,
        "density_skip_threshold": float(density_skip_threshold),
        "cluster_weighted_mean_density": density_gate_info.get("cluster_weighted_mean_density"),
        "subcluster_weighted_mean_density": density_gate_info.get("subcluster_weighted_mean_density"),
        "density_sum": density_gate_info.get("density_sum"),
        "force_all_one_weights": bool(density_gate_triggered),
        "requested_weights": {
            "intra_subcluster_weight": float(intra_subcluster_weight),
            "intra_cluster_weight": float(intra_cluster_weight),
            "inter_cluster_weight": float(inter_cluster_weight),
        },
        "effective_weights": {
            "intra_subcluster_weight": float(effective_intra_subcluster_weight),
            "intra_cluster_weight": float(effective_intra_cluster_weight),
            "inter_cluster_weight": float(effective_inter_cluster_weight),
        },
        "analysis_method": density_gate_info.get("method"),
        "subcluster_net_source": density_gate_info.get("subcluster_net_source"),
    }
    density_gate_summary_file = os.path.join(reweighting_output, "density_gate_summary.json")
    try:
        with open(density_gate_summary_file, "w", encoding="utf-8") as f:
            json.dump(density_gate_summary, f, indent=2, ensure_ascii=False)
        print(f"  [Density Gate] Summary saved: {density_gate_summary_file}")
    except Exception as e:
        print(f"  [Density Gate] Warning: failed to save summary JSON: {e}")
    
    try:
        from net_reweighting_integration import NetReweightingIntegration
        
        reweight_integrator = NetReweightingIntegration(
            benchmark_dir=benchmark_dir,
            output_dir=reweighting_output
        )
        
        reweight_files = reweight_integrator.run(
            cluster_layouts=pipeline.cluster_layouts,
            clustering_results=pipeline.clustering_results if hasattr(pipeline, 'clustering_results') else None,
            intra_subcluster_weight=effective_intra_subcluster_weight,
            intra_cluster_weight=effective_intra_cluster_weight,
            inter_cluster_weight=effective_inter_cluster_weight
        )
        
        wts_file = reweight_files.get('wts')
        print(f"\n  Net weights file: {wts_file}")
        
    except ImportError:
        print("Warning: net_reweighting_integration not found")
        wts_file = None

    phase_timings['Phase 3: Net Reweighting'] = time.time() - phase3_t0
    print(f"\n  [Timing] Phase 3 completed in {phase_timings['Phase 3: Net Reweighting']:.1f}s")

    # =========================================================================
    # Phase 4: Prepare Final DREAMPlaceFPGA Input
    # =========================================================================
    phase4_t0 = time.time()
    print("\n" + "=" * 80)
    print("PHASE 4: Prepare Final DREAMPlaceFPGA Input")
    print("=" * 80)
    
    # 复制benchmark文件（不包括.pl文件）
    print("\n[4.1] Copying benchmark files...")
    benchmark_copy_exts = {'.nodes', '.nets', '.scl', '.lib', '.regions', '.cascade_shape', '.macros'}
    benchmark_sidecars = {'design.clk', 'design.timing', 'design.clock_nets', 'design.metadata.json'}
    for f in os.listdir(benchmark_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in benchmark_copy_exts or f in benchmark_sidecars:
            src = os.path.join(benchmark_dir, f)
            dst = os.path.join(final_output, f)
            shutil.copy2(src, dst)
            print(f"  Copied: {f}")
    
    # 确保新增的可选文件存在（即使为空），避免DREAMPlaceFPGA解析aux时报错
    optional_placeholders = ["design.regions", "design.cascade_shape", "design.macros"]
    for _fname in optional_placeholders:
        _fpath = os.path.join(final_output, _fname)
        if not os.path.exists(_fpath):
            open(_fpath, "w").close()
            print(f"  Created empty optional file: {_fname}")
    
    # 处理placement文件
    print("\n[4.2] Setting up placement files...")
    movable_init_dst = None
    fixed_pl_dst = None
    
    if init_pl_file and os.path.exists(init_pl_file):
        # 复制可移动节点初始布局
        movable_init_dst = os.path.join(final_output, "movable_init.pl")
        shutil.copy2(init_pl_file, movable_init_dst)
        print(f"  Movable init: movable_init.pl")
        
        # 复制固定节点文件
        if fixed_pl_file and os.path.exists(fixed_pl_file):
            fixed_pl_dst = os.path.join(final_output, "design.pl")
            shutil.copy2(fixed_pl_file, fixed_pl_dst)
            print(f"  Fixed nodes: design.pl")
        else:
            # 备选：查找同目录的design.pl
            fixed_pl_src = os.path.join(os.path.dirname(init_pl_file), "design.pl")
            if os.path.exists(fixed_pl_src):
                fixed_pl_dst = os.path.join(final_output, "design.pl")
                shutil.copy2(fixed_pl_src, fixed_pl_dst)
                print(f"  Fixed nodes: design.pl (from same directory)")
    else:
        # 复制原始.pl文件（只有固定节点）
        for f in os.listdir(benchmark_dir):
            if f.endswith('.pl'):
                src = os.path.join(benchmark_dir, f)
                dst = os.path.join(final_output, "design.pl")
                shutil.copy2(src, dst)
                fixed_pl_dst = dst
                print(f"  Copied original: {f} -> design.pl")
                break
    
    # 复制.wts文件
    print("\n[4.3] Setting up net weights...")
    weights_dst = None
    if wts_file and os.path.exists(wts_file):
        base = os.path.splitext(os.path.basename(wts_file))[0]
        weights_name = base + ".weights"
        weights_dst = os.path.join(final_output, weights_name)
        shutil.copy2(wts_file, weights_dst)
        print(f"  Net weights (renamed): {weights_name}")
    else:
        print("  No net weights file (will still create empty .wts placeholder)")

    # 创建空的 .wts placeholder
    wts_dst = os.path.join(final_output, "design.wts")
    open(wts_dst, "w").close()
    print(f"  Created empty placeholder: {os.path.basename(wts_dst)}")
        
    # 生成.aux文件
    print("\n[4.4] Generating .aux file...")
    aux_files = []
    for f in os.listdir(final_output):
        ext = os.path.splitext(f)[1].lower()
        if ext in ['.nodes', '.nets', '.scl', '.lib', '.wts']:
            aux_files.append(f)
        elif f == 'design.pl':
            aux_files.append(f)
    
    _order = {
        '.nodes': 0, '.nets': 1, '.wts': 2, '.pl': 3, '.scl': 4, '.lib': 5
    }
    def _aux_sort_key(name: str):
        ext = os.path.splitext(name)[1].lower()
        return (_order.get(ext, 99), name)
    aux_files = sorted(dict.fromkeys(aux_files), key=_aux_sort_key)
    aux_path = os.path.join(final_output, "design.aux")
    with open(aux_path, 'w') as f:
        f.write(f"design : {' '.join(aux_files)}\n")
    print(f"  Aux file: design.aux")
    print(f"  Contents: {' '.join(aux_files)}")
    
    # 生成config文件
    print("\n[4.5] Generating DREAMPlaceFPGA config...")
    config = {
        "aux_input": aux_path,
        "init_placement_file": movable_init_dst if movable_init_dst else "",
        "net_weight_file": weights_dst if weights_dst else "",
        "gpu": gpu,
        "num_threads": 8,
        "num_bins_x": 512,
        "num_bins_y": 512,
        #"max_num_area_adjust" : 1,
        "global_place_stages": [
            {
                "num_bins_x": 512,
                "num_bins_y": 512,
                "iteration": final_iteration,
                "learning_rate": learning_rate,
                "wirelength": "weighted_average",
                "optimizer": "nesterov"
            }
        ],
        "trace_cells_flag": 1,
        "trace_cells_num": 100,
        "trace_cells_interval": 1,
        "trace_cells_init_pl": "movable_init.pl",
        "result_dir": "results",
        "routability_opt_flag": int(routability_opt_flag),
        "target_density": 1.0,
        "density_weight": float(density_weight),
        "random_seed": int(random_seed),
        "scale_factor": 1.0,
        "global_place_flag": 1,
        "legalize_flag": 0,
        "detailed_place_flag": 0,
        "dtype": "float32",
        "deterministic_flag": 1,
        "random_center_init_flag": 0,
        "node_area_adjust_overflow": float(node_area_adjust_overflow),
        "gamma": float(gamma)

    }
    if net_weight_anneal_iters and int(net_weight_anneal_iters) > 0:
        config["global_place_stages"][0]["net_weight_anneal_iters"] = int(net_weight_anneal_iters)
    config_path = os.path.join(final_output, "dreamplace_config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"  Config file: dreamplace_config.json")
    print(f"  aux_input: {config['aux_input']}")
    print(f"  init_placement_file: {config['init_placement_file']}")
    print(f"  net_weight_file: {config['net_weight_file']}")
    print(f"  random_center_init_flag: {config['random_center_init_flag']}")

    final_run_output = final_output
    final_run_config_path = config_path
    compat_summary_path = None
    if final_dreamplace_compat:
        print("\n[4.6] Generating DREAMPlaceFPGA compatibility view for final placement...")
        final_run_output, final_run_config_path, compat_summary_path = _prepare_dreamplace_compat_final_input(
            final_output=final_output,
            config=config,
        )
        print("  Real final input remains unchanged: 4_final_input/")
        print(f"  Compat final input: {final_run_output}")
        print(f"  Compat config: {final_run_config_path}")
        print(f"  Compat summary: {compat_summary_path}")

    final_input_dir = final_output
    phase_timings['Phase 4: Prepare Final Input'] = time.time() - phase4_t0
    print(f"\n  [Timing] Phase 4 completed in {phase_timings['Phase 4: Prepare Final Input']:.1f}s")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 80)
    print("FLOW COMPLETED!")
    print("=" * 80)
    
    print("\n[Output Structure]")
    print(f"  {output_base_dir}/")
    print(f"  ├── 1_clustering/          # Clustering results & visualizations")
    print(f"  ├── 2_cluster_placement/   # Cluster-level placement")
    print(f"  ├── 3_net_reweighting/     # Net weights based on clustering")
    print(f"  └── 4_final_input/         # Final DREAMPlaceFPGA input")
    
    print("\n[Key Files]")
    print(f"  Cluster layouts: {layouts_file}")
    print(f"  Clustering results: {results_file}")
    if init_pl_file:
        print(f"  Initial placement: {init_pl_file}")
    if wts_file:
        print(f"  Net weights: {wts_file}")
    print(f"  Final config: {config_path}")
    if final_dreamplace_compat:
        print(f"  DREAMPlace-compatible final config: {final_run_config_path}")
    
    print("\n[Log Files]")
    cluster_log = os.path.join(cluster_placement_output, 'cluster_placement', 'cluster_placement.log')
    if os.path.exists(cluster_log):
        print(f"  Cluster placement log: {cluster_log}")
    final_log = os.path.join(final_run_output, 'final_placement.log')
    print(f"  Final placement log: {final_log} (will be created when running final placement)")
    
    print("\n[Configuration Summary]")
    print(f"  Clustering:")
    print(f"    min_cluster_size: {min_cluster_size}")
    print(f"    louvain_resolution: {louvain_resolution}")
    print(f"    gift_scale: {gift_scale}")
    print(f"    macro_neighbor_depth: {macro_neighbor_depth}")
    print(f"  Net Reweighting:")
    print(f"    density_skip_threshold: {density_skip_threshold}")
    print(f"    density_gate_triggered: {density_gate_triggered}")
    if density_gate_info.get("success"):
        print(f"    cluster_weighted_mean_density: {density_gate_info.get('cluster_weighted_mean_density'):.6f}")
        print(f"    subcluster_weighted_mean_density: {density_gate_info.get('subcluster_weighted_mean_density'):.6f}")
        print(f"    density_sum: {density_gate_info.get('density_sum'):.6f}")
    else:
        print(f"    density_analysis_error: {density_gate_info.get('error')}")
    print(f"    requested_intra_subcluster_weight: {intra_subcluster_weight}")
    print(f"    requested_intra_cluster_weight: {intra_cluster_weight}")
    print(f"    requested_inter_cluster_weight: {inter_cluster_weight}")
    print(f"    effective_intra_subcluster_weight: {effective_intra_subcluster_weight}")
    print(f"    effective_intra_cluster_weight: {effective_intra_cluster_weight}")
    print(f"    effective_inter_cluster_weight: {effective_inter_cluster_weight}")
    if density_gate_summary_file:
        print(f"    density_gate_summary_file: {density_gate_summary_file}")
    print(f"  Final Placement:")
    print(f"    iteration: {final_iteration}")
    print(f"    learning_rate: {learning_rate}")
    print(f"    gpu: {gpu}")
    
    print("\n[Next Step: Run Final Placement]")
    placer_script = None
    if dreamplace_path:
        placer_script = os.path.join(dreamplace_path, "dreamplacefpga", "Placer.py")
        print(f"  python {placer_script} {final_run_config_path}")
    else:
        print(f"  python dreamplacefpga/Placer.py {final_run_config_path}")
    
    # 可选：自动运行最终 placement
    if run_final_placement:
        phase5_t0 = time.time()
        if not placer_script or not os.path.exists(placer_script):
            print("\n[Final Placement] Skip: Placer.py not found.")
            print("  Please set --dreamplace_path /path/to/DREAMPlaceFPGA, or ensure dreamplacefpga/Placer.py exists next to this script.")
        else:
            log_file = os.path.join(final_run_output, "final_placement.log")
            cmd = [sys.executable, placer_script, final_run_config_path]
            print("\n[Final Placement] Running...")
            print(f"  CWD: {final_run_output}")
            print(f"  CMD: {' '.join(cmd)}")
            print(f"  LOG: {log_file}")
            env = os.environ.copy()
            if dreamplace_path and os.path.exists(dreamplace_path):
                env["PYTHONPATH"] = dreamplace_path + os.pathsep + env.get("PYTHONPATH", "")

            try:
                with open(log_file, "w") as lf:
                    result = subprocess.run(
                        cmd,
                        cwd=final_run_output,
                        env=env,
                        stdout=lf,
                        stderr=lf,
                        text=True,
                    )

                if result.returncode == 0:
                    print("  Final placement completed successfully.")
                    print(f"  Results: {os.path.join(final_run_output, 'results')}")
                    print(f"  Log: {log_file}")
                    _report_dreamplace_convergence(log_file, "Final placement")

                    # 绘制 metrics 曲线
                    plot_script = os.path.join(os.path.dirname(placer_script), "plot_placement_metrics.py")
                    if not os.path.exists(plot_script):
                        local_plot = os.path.join(script_dir, "plot_placement_metrics.py")
                        if os.path.exists(local_plot):
                            plot_script = local_plot

                    if os.path.exists(plot_script):
                        metrics_png = os.path.join(final_run_output, "placement_metrics.png")
                        plot_log = os.path.join(final_run_output, "plot_placement_metrics.log")
                        plot_cmd = [sys.executable, plot_script, "--log", log_file, "--output", metrics_png]

                        print("\n[Plot Placement Metrics] Running...")
                        print(f"  CMD: {' '.join(plot_cmd)}")
                        print(f"  OUT: {metrics_png}")
                        print(f"  LOG: {plot_log}")

                        with open(plot_log, "w") as pf:
                            plot_ret = subprocess.run(
                                plot_cmd,
                                cwd=final_run_output,
                                env=env,
                                stdout=pf,
                                stderr=pf,
                                text=True,
                            )

                        if plot_ret.returncode == 0 and os.path.exists(metrics_png):
                            print("  Metrics curve generated successfully.")
                        else:
                            print(f"  Warning: metrics plotting failed (returncode={plot_ret.returncode}).")
                            print(f"  Check log: {plot_log}")
                    else:
                        print("  Warning: plot_placement_metrics.py not found; skip plotting.")
                else:
                    print(f"  Warning: final placement failed (returncode={result.returncode}).")
                    print(f"  Check log: {log_file}")
            except Exception as e:
                print(f"  Warning: Failed to run final placement: {e}")
                print(f"  Check log: {log_file}")

        phase_timings['Phase 5: Final Placement'] = time.time() - phase5_t0
        print(f"\n  [Timing] Phase 5 completed in {phase_timings['Phase 5: Final Placement']:.1f}s")

    # =========================================================================
    # Timing Summary
    # =========================================================================
    total_elapsed = time.time() - flow_t0
    print("\n" + "=" * 80)
    print("TIMING SUMMARY")
    print("=" * 80)
    print(f"  {'Phase':<35} {'Time (s)':>10} {'% Total':>10}")
    print(f"  {'-'*35} {'-'*10} {'-'*10}")
    for phase_name, elapsed in phase_timings.items():
        pct = (elapsed / total_elapsed * 100) if total_elapsed > 0 else 0
        print(f"  {phase_name:<35} {elapsed:>10.1f} {pct:>9.1f}%")
    print(f"  {'-'*35} {'-'*10} {'-'*10}")
    print(f"  {'TOTAL':<35} {total_elapsed:>10.1f} {'100.0%':>10}")
    print("=" * 80)

    return {
        'cluster_layouts_file': layouts_file,
        'clustering_results_file': results_file,
        'init_placement_file': init_pl_file,
        'wts_file': wts_file,
        'density_gate_summary_file': density_gate_summary_file,
        'config_file': config_path,
        'dreamplace_compat_config_file': final_run_config_path if final_dreamplace_compat else None,
        'final_output_dir': final_output
    }



def _coerce_bool(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(int(x))
    if isinstance(x, str):
        s = x.strip().lower()
        if s in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "f", "no", "n", "off"}:
            return False
    # Fallback: Python truthiness
    return bool(x)


def _flatten_json_params(obj):
    """Support two styles:
    1) Simple values: {"min_cluster_size": 100, "gpu": 1, ...}
    2) Schema-like dicts (like paramsFPGA.json): {"gpu": {"default": 1, ...}, ...}
       We treat key['value'] (if exists) else key['default'] as the actual value.
    Also supports optional top-level sections:
      {"clustering": {...}, "cluster_placement": {...}, "net_reweighting": {...}, ...}
    """
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object/dict")

    # If user provides sectioned config, merge sections into one flat dict.
    section_keys = {
        "clustering",
        "cluster_placement",
        "benchmark_conversion",
        "net_reweighting",
        "final_placement",
        "dreamplace",
        "misc",
    }
    # Keys that are scalar flags, not sections — pass through directly
    _passthrough_keys = {"adaptive", "adaptive_profiles"}
    flat = {}

    def ingest(d):
        for k, v in d.items():
            if isinstance(v, dict):
                # schema-like
                if "value" in v:
                    flat[k] = v["value"]
                elif "default" in v:
                    flat[k] = v["default"]
                else:
                    # treat as nested sectionless dict -> ignore (or user mistake)
                    # do nothing to avoid accidental deep merges
                    pass
            else:
                flat[k] = v

    # detect sectioned config
    has_sections = any(k in section_keys and isinstance(obj.get(k), dict) for k in obj.keys())
    if has_sections:
        for k, v in obj.items():
            if k in section_keys and isinstance(v, dict):
                ingest(v)
            elif k not in section_keys:
                # still allow top-level keys alongside sections
                ingest({k: v})
    else:
        ingest(obj)

    return flat


def _load_params_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _flatten_json_params(data)


def _apply_json_params_to_args(parser: argparse.ArgumentParser, args: argparse.Namespace, cfg: dict, argv: list):
    """Apply cfg onto args *only if* the corresponding CLI option was not explicitly provided."""
    # Build dest -> option_strings map
    dest_to_opts = {}
    for action in parser._actions:
        if not action.option_strings:
            continue
        dest_to_opts[action.dest] = list(action.option_strings)

    def was_provided(dest: str) -> bool:
        opts = dest_to_opts.get(dest, [])
        for opt in opts:
            if opt in argv:
                return True
            # handle --opt=value
            if any(a.startswith(opt + "=") for a in argv):
                return True
        return False

    # Aliases: allow JSON to use run_complete_flow signature names too
    alias_to_dest = {
        "louvain_resolution": "resolution",
        "specpart_ub_factor": "ub_factor",
        "intra_subcluster_weight": "intra_sub",
        "intra_cluster_weight": "intra",
        "inter_cluster_weight": "inter",
        "output_base_dir": "output_dir",
        "aux_file": "aux",
        "run_cluster_placement": "no_cluster_placement",  # inverted logic
        "visualize": "no_viz",                             # inverted logic
    }

    for key, val in cfg.items():
        dest = alias_to_dest.get(key, key)
        if not hasattr(args, dest):
            continue

        # Special inverted flags
        if key == "run_cluster_placement":
            if not was_provided("no_cluster_placement"):
                setattr(args, "no_cluster_placement", not _coerce_bool(val))
            continue
        if key == "visualize":
            if not was_provided("no_viz"):
                setattr(args, "no_viz", not _coerce_bool(val))
            continue

        # Normal fields
        if was_provided(dest):
            continue  # CLI wins

        # Coerce booleans for store_true flags if user sets them in JSON
        if dest in {
            "no_cluster_placement",
            "no_viz",
            "run_final_placement",
            "final_dreamplace_compat",
            "skip_clustering",
            "convert_public_release",
            "keep_converted_benchmark",
        }:
            setattr(args, dest, _coerce_bool(val))
        else:
            setattr(args, dest, val)

    return args


def main():
    parser = argparse.ArgumentParser(
        description='Complete FPGA Placement Flow with Clustering (Enhanced)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
完整流程说明:
  1. Louvain聚类: 将设计分为若干大cluster
  2. GIFT布局: 对每个cluster进行布局优化
  3. SpecPart: 对每个cluster进行sub-clustering
  4. Cluster Placement: 将sub-clusters作为节点进行global placement
  5. 初始布局生成: 在每个cluster内分配单元位置
  6. Net Reweighting: 基于clustering调整网络权重
  7. 最终输入准备: 生成DREAMPlaceFPGA所需的所有输入文件

示例:
  # 基本用法
  python run_complete_flow_enhanced.py --benchmark_dir benchmarks/design1 --output_dir output
  
  # 指定DREAMPlaceFPGA路径
  python run_complete_flow_enhanced.py --benchmark_dir benchmarks/design1 \\
      --dreamplace_path /path/to/DREAMPlaceFPGA --output_dir output
  
  # 从cluster placement开始（跳过聚类）
  python run_complete_flow_enhanced.py --benchmark_dir benchmarks/design1 \\
      --dreamplace_path /path/to/DREAMPlaceFPGA --output_dir output --skip_clustering
  
  # 自定义参数
  python run_complete_flow_enhanced.py --benchmark_dir benchmarks/design1 \\
      --min_cluster_size 100 --gift_scale 0.3 \\
      --intra_sub 2.0 --inter 0.6 \\
      --output_dir output

权重策略说明:
  --intra_sub: 同一sub-cluster内的网络权重 (>1 鼓励紧凑)
  --intra:     同一cluster内跨sub-cluster的网络权重
  --inter:     跨cluster的网络权重 (<1 减少约束)
        """
    )
    
    # 输入输出
    parser.add_argument('--benchmark_dir', type=str, default=None,
                   help='FPGA benchmark目录（可在CLI或params_json中提供）')
    parser.add_argument('--output_dir', type=str, default='./output',
                       help='输出目录')
    parser.add_argument('--aux', type=str, default=None,
                       help='.aux文件名')
    parser.add_argument('--dreamplace_path', type=str, default=None,
                       help='DREAMPlaceFPGA路径')

    parser.add_argument('--params_json', type=str, default=None,
                       help='从JSON读取所有参数（CLI参数优先覆盖JSON）。支持两种格式：'
                            '1) 简单键值对；2) 类似 paramsFPGA.json 的 {key:{default:...}}。')

    # Benchmark format conversion
    parser.add_argument('--convert_public_release', action='store_true',
                        help='先将 public_release/case_N + Arch 转换为本流程兼容的 design.* Bookshelf 输入')
    parser.add_argument('--convert_arch_dir', type=str, default=None,
                        help='public_release 转换使用的架构目录，默认 PROJECT_ROOT/Arch')
    parser.add_argument('--convert_case', type=str, default=None,
                        help='要转换的 public_release case 名称，例如 case_1')
    parser.add_argument('--converted_benchmark_dir', type=str, default=None,
                        help='转换后 benchmark 输出目录，默认 output_dir/_converted_benchmark/<case>')
    parser.add_argument('--keep_converted_benchmark', action='store_true',
                        help='保留转换目录中的已有文件；默认每次覆盖转换输出')
    
    # Clustering参数
    parser.add_argument('--min_cluster_size', type=int, default=50,
                       help='Louvain最小cluster大小 (default: 50)')
    parser.add_argument('--resolution', type=float, default=1.0,
                       help='Louvain分辨率 (default: 1.0)')
    parser.add_argument('--gift_scale', type=float, default=0.5,
                       help='GIFT初始位置范围 (default: 0.5)')
    parser.add_argument('--ub_factor', type=int, default=10,
                       help='SpecPart不平衡因子 (default: 10)')
    parser.add_argument('--num_trees', type=int, default=5,
                       help='SpecPart树数量 (default: 5)')

    parser.add_argument('--best_solns', type=int, default=5,
                       help='SpecPart选择的最佳解数量 (default: 5)')
    parser.add_argument('--specpart_num_seeds', type=int, default=5,
                        help='Number of perturbed seeds to run SpecPart with, picking best cutsize (default: 5)')
    parser.add_argument('--specpart_timeout', type=int, default=3600,
                        help='Timeout in seconds for each K_SpecPart sub-batch Julia process (default: 3600)')
    parser.add_argument('--specpart_per_job_timeout', type=int, default=120,
                        help='Per-job timeout budget in seconds for scaling sub-batch timeout (default: 120)')
    parser.add_argument('--specpart_num_workers', type=int, default=15,
                        help='Number of parallel Julia workers for K_SpecPart (default: 4)')
    parser.add_argument('--specpart_mode', type=str, default='gift_then_spectral',
                        choices=['gift_single', 'gift_then_spectral', 'louvain_kway'],
                        help='SpecPart mode: '
                             '"gift_single" = one-shot GIFT tree_partition + overlay (no iteration, fast); '
                             '"gift_then_spectral" = first iter uses GIFT, subsequent iters use spectral solve_eigs; '
                             '"louvain_kway" = disable GIFT, run full K_SpecPart directly on Louvain clusters in parallel '
                             '(default: gift_then_spectral)')
    parser.add_argument('--max_cluster_size', type=int, default=None,
                        help='Louvain clusters larger than this will be recursively split (default: None)')
    parser.add_argument('--macro_neighbor_depth', type=int, default=-1,
                        help='Neighbor layers around each macro for locked clusters: '
                             '-1=no macro locking, 0=macro only, 1=1-hop neighbors (default), 2=2-hop, ...')
    parser.add_argument('--cluster_random_seed', type=int, default=42,
                        help='统一随机种子：控制 clustering / cluster placement / dreamplace config 等 (default: 42)')
    # Cluster placement参数
    parser.add_argument('--no_cluster_placement', action='store_true',
                       help='跳过cluster-level placement')
    parser.add_argument('--cluster_iteration', type=int, default=1000,
                       help='Cluster placement迭代次数 (default: 1000)')
    parser.add_argument('--place_density_lb_addon', type=float, default=0.0,
                    help='(NEW) place_density = lb + (1-lb)*addon + 0.01; addon建议[0,0.99],但也可以超过，具体判断我注释掉了')

    parser.add_argument('--utilization', type=float, default=0.8,
                       help='Cluster-level size utilization for virtual nodes (default: 0.8)')
    parser.add_argument('--sigma_ratio', type=float, default=0.95,
                       help='Sigma ratio for scattering inside each subcluster (default: 0.95)')
    parser.add_argument('--scatter_mode', type=str, default="gaussian_circle",
                        choices=["gaussian_circle", "uniform_rect"],
                        help='Cell scattering mode inside cluster: gaussian_circle (default) or uniform_rect')
    parser.add_argument('--max_fanout', type=int, default=0,
                       help='Max fanout threshold when building cluster hypergraph; 0/negative disables filtering (default: 200)')
    parser.add_argument('--cluster_base_weight', type=float, default=0.1,
                        help='Base net weight for cluster-level nets (default: 1.0)')
    parser.add_argument('--cluster_fixed_cluster_weight', type=float, default=5.0,
                        help='Boosted net weight for nets containing both fixed and cluster_* (default: 10.0)')
    # Net reweighting参数
    parser.add_argument('--intra_sub', type=float, default=1.5,
                       help='同一sub-cluster内网络权重 (default: 1.5)')
    parser.add_argument('--intra', type=float, default=1.0,
                       help='同一cluster内跨sub-cluster网络权重 (default: 1.0)')
    parser.add_argument('--inter', type=float, default=0.8,
                       help='跨cluster网络权重 (default: 0.8)')
    parser.add_argument('--density_skip_threshold', type=float, default=1.3,
                       help='若 cluster/subcluster 加权平均 net_density 之和超过该阈值，则强制 net weights 全为1 (default: 1.3)')
    
    # Final placement参数
    parser.add_argument('--gpu', type=int, default=0,
                       help='是否使用GPU (default: 0)')
    parser.add_argument('--final_iteration', type=int, default=2000,
                       help='最终placement迭代次数 (default: 2000)')
    parser.add_argument('--learning_rate', type=float, default=0.01,
                       help='学习率 (default: 0.01)')
    parser.add_argument('--net_weight_anneal_iters', type=int, default=0,
                        help='net weight anneal iterations for DreamPlaceFPGA (default: 0)')
    parser.add_argument('--density_weight', type=float, default=0.01,
                        help='DreamPlace density_weight (default: 0.01)')
    parser.add_argument('--node_area_adjust_overflow', type=float, default=0.1,
                        help='DreamPlace node_area_adjust_overflow (default: 0.1)')
    parser.add_argument('--gamma', type=float, default=0.8,
                        help='DreamPlace gamma parameter (default: 0.8)')
    parser.add_argument('--routability_opt_flag', type=int, default=1) 
    parser.add_argument('--random_seed', type=int, default=1000)                  
    # 其他
    parser.add_argument('--no_viz', action='store_true',
                       help='不生成可视化')
    parser.add_argument('--run_final_placement', action='store_true',
                    help='在生成 4_final_input 后，直接运行最终 placement (Placer.py)')
    parser.add_argument('--final_dreamplace_compat', action='store_true',
                    help='为当前 DREAMPlaceFPGA 额外生成 4_final_input_dreamplace_compat 并在该目录运行；不修改真实 4_final_input')
    
    # 新增: 跳过聚类阶段
    parser.add_argument('--skip_clustering', action='store_true',
                       help='跳过聚类阶段，从已有的聚类结果开始（用于恢复运行）')

    # Adaptive parameter selection
    parser.add_argument('--adaptive', action='store_true',
                        help='Auto-select parameters based on design characteristics (KNN from tuner data)')
    parser.add_argument('--adaptive_profiles', type=str, default=None,
                        help='Path to custom adaptive_profiles.json (default: adaptive_profiles.json next to this script)')
    
    args = parser.parse_args()

    # --- Load JSON params (if any) ---
    cfg = {}
    if args.params_json:
        args.params_json = _resolve_project_path(args.params_json)
        try:
            cfg = _load_params_json(args.params_json)
            _apply_json_params_to_args(parser, args, cfg, sys.argv[1:])
            print(f"Loaded params from JSON: {args.params_json}")
        except Exception as e:
            print(f"Error: Failed to load params_json={args.params_json}: {e}")
            sys.exit(1)

    if args.benchmark_dir is None:
        parser.error("--benchmark_dir is required (either via CLI or params_json)")

    args.benchmark_dir = _resolve_project_path(args.benchmark_dir)
    args.output_dir = _resolve_project_path(args.output_dir)
    args.dreamplace_path = _resolve_project_path(args.dreamplace_path)
    args.adaptive_profiles = _resolve_project_path(args.adaptive_profiles)
    args.convert_arch_dir = _resolve_project_path(args.convert_arch_dir)
    args.converted_benchmark_dir = _resolve_project_path(args.converted_benchmark_dir)

    if args.convert_public_release:
        try:
            from convert_public_release_benchmark import (
                convert_public_release_case,
                infer_public_release_case,
            )

            public_release_dir, case_name = infer_public_release_case(
                Path(args.benchmark_dir),
                args.convert_case,
            )
            arch_dir = args.convert_arch_dir or os.path.join(PROJECT_ROOT, "Arch")
            converted_dir = args.converted_benchmark_dir
            if converted_dir is None:
                converted_dir = os.path.join(args.output_dir, "_converted_benchmark", case_name)

            print("=" * 80)
            print("Benchmark Conversion: public_release -> pipeline Bookshelf")
            print("=" * 80)
            print(f"  source_dir: {public_release_dir}")
            print(f"  case:       {case_name}")
            print(f"  arch_dir:   {arch_dir}")
            print(f"  output_dir: {converted_dir}")

            args.benchmark_dir = convert_public_release_case(
                public_release_dir=str(public_release_dir),
                arch_dir=str(arch_dir),
                case_name=case_name,
                output_dir=converted_dir,
                overwrite=not args.keep_converted_benchmark,
            )
            if args.aux is None:
                args.aux = "design.aux"
        except Exception as e:
            print(f"Error: public_release benchmark conversion failed: {e}")
            sys.exit(1)

    # --- Adaptive parameter selection ---
    # Priority: CLI args > JSON keys > adaptive params > argparse defaults
    # Check if adaptive mode requested via CLI flag or JSON key
    adaptive_enabled = args.adaptive or _coerce_bool(cfg.get("adaptive", False))
    adaptive_profiles_path = args.adaptive_profiles or cfg.get("adaptive_profiles", None)

    if adaptive_enabled:
        from adaptive_params import compute_adaptive_params
        adaptive_cfg = compute_adaptive_params(args.benchmark_dir, adaptive_profiles_path)

        # Determine which param keys the user explicitly set (via CLI or JSON)
        # so we never override those with adaptive values.
        dest_to_opts = {}
        for action in parser._actions:
            if not action.option_strings:
                continue
            dest_to_opts[action.dest] = list(action.option_strings)

        def _was_cli_provided(dest: str) -> bool:
            opts = dest_to_opts.get(dest, [])
            for opt in opts:
                if opt in sys.argv[1:]:
                    return True
                if any(a.startswith(opt + "=") for a in sys.argv[1:]):
                    return True
            return False

        # Alias map: adaptive key -> argparse dest
        _adaptive_alias = {
            "louvain_resolution": "resolution",
            "specpart_ub_factor": "ub_factor",
            "intra_subcluster_weight": "intra_sub",
            "intra_cluster_weight": "intra",
            "inter_cluster_weight": "inter",
        }

        # Keys the user explicitly set in JSON (excluding meta keys)
        _json_explicit = set(cfg.keys()) - {"adaptive", "adaptive_profiles"}

        # Seeds are never set by adaptive
        _adaptive_skip = {"cluster_random_seed", "random_seed"}

        applied = []
        for key, val in adaptive_cfg.items():
            if key in _adaptive_skip:
                continue
            dest = _adaptive_alias.get(key, key)
            if not hasattr(args, dest):
                continue
            # Skip if user explicitly provided via CLI
            if _was_cli_provided(dest):
                continue
            # Skip if user explicitly provided via JSON (check both original key and dest)
            if key in _json_explicit or dest in _json_explicit:
                continue
            # Also check aliases in JSON
            alias_hit = False
            for json_key, json_dest in {
                "louvain_resolution": "resolution",
                "specpart_ub_factor": "ub_factor",
                "intra_subcluster_weight": "intra_sub",
                "intra_cluster_weight": "intra",
                "inter_cluster_weight": "inter",
            }.items():
                if json_dest == dest and json_key in _json_explicit:
                    alias_hit = True
                    break
            if alias_hit:
                continue
            setattr(args, dest, val)
            applied.append(dest)

        if applied:
            print(f"[adaptive] Applied {len(applied)} adaptive params: {', '.join(sorted(applied))}")

    terminal_log_path = _enable_terminal_logging(args.output_dir)
    print(f"Terminal output will also be saved to: {terminal_log_path}")
    # 检查 dreamplace_path
    if args.skip_clustering and not args.dreamplace_path:
        print("=" * 80)
        print("WARNING: Using --skip_clustering without --dreamplace_path")
        print("=" * 80)
        print("\nCluster placement requires DREAMPlaceFPGA. Without it, only random")
        print("placement will be used. For best results, please provide:")
        print("  --dreamplace_path /path/to/DREAMPlaceFPGA")
        print("")
    
    run_complete_flow(
        benchmark_dir=args.benchmark_dir,
        output_base_dir=args.output_dir,
        aux_file=args.aux,
        min_cluster_size=args.min_cluster_size,
        louvain_resolution=args.resolution,
        gift_scale=args.gift_scale,
        specpart_ub_factor=args.ub_factor,
        num_trees=args.num_trees,
        max_cluster_size=args.max_cluster_size,
        macro_neighbor_depth=args.macro_neighbor_depth,
        specpart_num_seeds=args.specpart_num_seeds,
        specpart_timeout=args.specpart_timeout,
        specpart_num_workers=args.specpart_num_workers,
        specpart_per_job_timeout=args.specpart_per_job_timeout,
        best_solns=args.best_solns,
        run_cluster_placement=not args.no_cluster_placement,
        cluster_iteration=args.cluster_iteration,
        place_density_lb_addon=args.place_density_lb_addon,
        utilization=args.utilization,
        sigma_ratio=args.sigma_ratio,
        max_fanout=(None if args.max_fanout is None or int(args.max_fanout) <= 0 else int(args.max_fanout)),
        intra_subcluster_weight=args.intra_sub,
        intra_cluster_weight=args.intra,
        inter_cluster_weight=args.inter,
        density_skip_threshold=args.density_skip_threshold,
        gpu=args.gpu,
        net_weight_anneal_iters=args.net_weight_anneal_iters,
        final_iteration=args.final_iteration,
        learning_rate=args.learning_rate,
        gamma=args.gamma,
        routability_opt_flag=args.routability_opt_flag,
        random_seed=args.random_seed,
        density_weight=args.density_weight,
        node_area_adjust_overflow=args.node_area_adjust_overflow,
        dreamplace_path=args.dreamplace_path,
        run_final_placement=args.run_final_placement,
        final_dreamplace_compat=args.final_dreamplace_compat,
        visualize=not args.no_viz,
        skip_clustering=args.skip_clustering,
        cluster_base_weight=args.cluster_base_weight,
        cluster_random_seed=args.cluster_random_seed,
        scatter_mode=args.scatter_mode,
        cluster_fixed_cluster_weight=args.cluster_fixed_cluster_weight,
        specpart_mode=args.specpart_mode
    )


if __name__ == "__main__":
    main()
