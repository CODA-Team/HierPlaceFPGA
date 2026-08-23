#!/usr/bin/env python3
"""
完整的FPGA聚类Pipeline - 带可视化 (修复版)
==========================================

修复内容:
- 正确传递parser和scl_file给可视化函数
- 确保fixed节点、IO节点、edges正确显示

功能:
1. Louvain聚类得到大clusters
2. 对每个大cluster运行GIFT布局
3. 可视化GIFT前后的节点位移(每个cluster + 综合图)
4. 对每个cluster运行SpecPart的Cut-Overlay聚类(不进行hMETIS分区)
5. 可视化Cut-Overlay聚类结果

用法:
    python main_pipeline_with_viz.py --benchmark_dir data/design --output_dir results
"""

import argparse
import os
import sys
import numpy as np
import json
import math
from scipy.sparse import csr_matrix
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
# 导入必要的模块
from fpga_clustering_pipeline_gift import FPGAClusteringPipeline
from visualization_clustering import (
    visualize_gift_pipeline,
    run_specpart_clustering_with_visualization,
    export_clustering_results
)
from gift_specpart_complete import GIFTSpecPartPipeline, DEFAULT_HMETIS_EXEC

def _cutoverlay_worker(job: dict):
    # 确保 worker 进程能找到同目录下的模块
    import sys
    import os
    _pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    if _pipeline_dir not in sys.path:
        sys.path.insert(0, _pipeline_dir)

    # 设置随机种子，确保可复现性
    import random
    import numpy as np
    import hashlib
    cluster_id = job["cluster_id"]
    base_seed = int(job.get("base_seed", 42))
    # ✅ 固定 seed = base_seed，不再加 MD5 偏移（与 batch 模式一致）
    seed = base_seed
    random.seed(seed)
    np.random.seed(seed)

    # ===== DEBUG PRINT #2 (worker process) =====
    try:
        hedges = job.get("hyperedges", [])
        hedge_max = max((max(h) for h in hedges), default=-1)
    except Exception:
        hedge_max = -1
    am = job.get("adj_matrix", None)
    print(f"[SpecPartWorker] cluster={cluster_id} seed={seed} "
        f"adj_shape={getattr(am, 'shape', None)} "
        f"adj_nnz={getattr(am, 'nnz', None)} "
        f"hyperedges={len(job.get('hyperedges', []))} hedge_max={hedge_max} "
        f"pos_shape={getattr(job.get('positions', None), 'shape', None)}")
    # =========================================
    clusters, cluster_map, stats = run_specpart_clustering_with_visualization(
        adj_matrix=job["adj_matrix"],
        hyperedges=job["hyperedges"],
        positions=job["positions"],
        node_indices=job["node_indices"],
        cluster_id_prefix=job["cluster_id_prefix"],
        ub_factor=job["ub_factor"],
        num_trees=job["num_trees"],
        best_solns=job["best_solns"],
        output_dir=job["cluster_viz_dir"],
        min_cluster_size=job.get("min_cluster_size", 50),
        use_hmetis=job.get("use_hmetis", True),
        hmetis_path=os.environ.get("HMETIS_EXEC", DEFAULT_HMETIS_EXEC),
        verbose=True,
        random_seed=seed
    )

    export_clustering_results(
        clusters=clusters,
        cluster_map=cluster_map,
        node_indices=job["node_indices"],
        output_dir=job["cluster_output_dir"],
        cluster_id_prefix=job["cluster_id_prefix"],
    )

    return cluster_id, {
        "clusters": clusters,
        "cluster_map": cluster_map,
        "stats": stats,
        "num_sub_clusters": len(clusters),
    }
class EnhancedFPGAPipeline:
    """
    增强的FPGA Pipeline - 集成可视化和聚类功能
    """
    
    def __init__(self, benchmark_dir, output_dir, cluster_random_seed: int = 42):
        # 设置全局随机种子，确保可复现性（由外部 cluster_random_seed 统一控制）
        import random
        self.cluster_random_seed = int(cluster_random_seed)

        # ✅ 用传入的 seed 统一控制
        random.seed(self.cluster_random_seed)
        np.random.seed(self.cluster_random_seed)
        
        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir
        self.viz_dir = os.path.join(output_dir, "visualizations")
        self.clustering_dir = os.path.join(output_dir, "clustering")
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.viz_dir, exist_ok=True)
        os.makedirs(self.clustering_dir, exist_ok=True)
        
        self.base_pipeline = None
        self.cluster_layouts = {}
        self.clustering_results = {}
        self.scl_file = None  # 保存.scl文件路径

    
    def run_full_pipeline(self, aux_file=None, min_cluster_size=50,
                         louvain_resolution=1.0, gift_scale=0.5,
                         specpart_ub_factor=10, num_trees=5, best_solns=5,
                         visualize_gift=False, run_specpart_clustering=True,
                         show_all_arrows=False, arrow_sample_ratio=0.5, max_cluster_size=None,
                         macro_neighbor_depth=-1, specpart_num_seeds=1,
                         specpart_timeout=3600, specpart_num_workers=10,
                         specpart_mode="gift_single", specpart_per_job_timeout=120,
                         max_fanout: int = 500):
        """
        运行完整Pipeline
        
        Args:
            aux_file: .aux文件
            min_cluster_size: Louvain最小cluster大小
            louvain_resolution: Louvain分辨率
            gift_scale: GIFT初始位置范围
            specpart_ub_factor: SpecPart不平衡因子
            num_trees: SpecPart树数量
            best_solns: SpecPart最佳解数量
            visualize_gift: 是否可视化GIFT结果
            run_specpart_clustering: 是否运行SpecPart聚类
            show_all_arrows: 是否显示所有节点箭头
            arrow_sample_ratio: 箭头采样比例
        """
        print("=" * 80)
        print("Enhanced FPGA Clustering Pipeline (Fixed Visualization)")
        print("=" * 80)
        
        # ============================================================
        # Phase 1: Louvain (+ optional GIFT)
        # ============================================================
        use_gift_layout = specpart_mode != "louvain_kway"
        print("\n" + "=" * 80)
        if use_gift_layout:
            print("PHASE 1: Louvain Clustering + GIFT Layout")
        else:
            print("PHASE 1: Louvain Clustering (GIFT Disabled)")
            print("  [Mode] louvain_kway: skip GIFT layout, run K_SpecPart directly on Louvain clusters")
        print("=" * 80)

        import time as _time
        _louvain_t0 = _time.time()
        self.base_pipeline = FPGAClusteringPipeline(self.benchmark_dir, self.output_dir)
        self.cluster_layouts = self.base_pipeline.run_pipeline(
            aux_file=aux_file,
            min_cluster_size=min_cluster_size,
            louvain_resolution=louvain_resolution,
            gift_scale=gift_scale,
            use_mixed_filter=True,
            cluster_random_seed=self.cluster_random_seed,
            max_cluster_size=max_cluster_size,
            macro_neighbor_depth=macro_neighbor_depth,
            max_fanout=max_fanout,
            run_gift_layout=use_gift_layout
        )
        phase1_name = "Louvain + GIFT" if use_gift_layout else "Louvain (no GIFT)"
        print(f"[Timing] {phase1_name} completed in {_time.time() - _louvain_t0:.1f}s")
        
        # 查找.scl文件
        self._find_scl_file()
        
        if len(self.cluster_layouts) == 0:
            print("\nWarning: No large clusters found!")
            return
        
        # ============================================================
        # Phase 2: GIFT可视化 (修复版)
        # ============================================================
        if visualize_gift and use_gift_layout:
            print("\n" + "=" * 80)
            print("PHASE 2: GIFT Displacement Visualization (Fixed)")
            print("=" * 80)
            
            # 关键修复: 传递parser和scl_file
            visualize_gift_pipeline(
                cluster_layouts=self.cluster_layouts, 
                output_dir=self.viz_dir,
                show_all_arrows=show_all_arrows,
                arrow_sample_ratio=arrow_sample_ratio,
                parser=self.base_pipeline.parser,  # 传递parser
                scl_file=self.scl_file  # 传递scl文件路径
            )
        elif visualize_gift and not use_gift_layout:
            print("  [GIFT] Visualization skipped in louvain_kway mode")
        
        # ============================================================
        # Phase 3: Cut-Overlay聚类
        # ============================================================
        if run_specpart_clustering:
            print("\n" + "=" * 80)
            print("PHASE 3: Cut-Overlay Clustering (without hMETIS)")
            print("=" * 80)
            
            self._run_cutoverlay_clustering(
                ub_factor=specpart_ub_factor,
                num_trees=num_trees,
                best_solns=best_solns,
                min_cluster_size=min_cluster_size,
                specpart_num_seeds=specpart_num_seeds,
                specpart_timeout=specpart_timeout,
                specpart_num_workers=specpart_num_workers,
                specpart_mode=specpart_mode,
                specpart_per_job_timeout=specpart_per_job_timeout
            )

        # ============================================================
        # Phase 4: Delayed assignment of isolated nodes
        # ============================================================
        if hasattr(self.base_pipeline, 'isolated_nodes') and self.base_pipeline.isolated_nodes:
            self.cluster_layouts, self.clustering_results = \
                self.base_pipeline.delayed_assign_isolated_nodes(
                    self.cluster_layouts, self.clustering_results)

        # ============================================================
        # 总结
        # ============================================================
        self._print_summary()
    
    def _find_scl_file(self):
        """查找.scl文件"""
        for f in os.listdir(self.benchmark_dir):
            if f.endswith('.scl'):
                self.scl_file = os.path.join(self.benchmark_dir, f)
                print(f"  Found .scl file: {f}")
                break
        
        if self.scl_file is None:
            print("  Warning: No .scl file found, IO sites will not be displayed")
        
    def _run_cutoverlay_clustering(self, ub_factor=10, num_trees=5, best_solns=5, min_cluster_size=50,
                                   specpart_num_seeds=1, specpart_timeout=3600, specpart_num_workers=10,
                                   specpart_mode="gift_single", specpart_per_job_timeout=120):

        import time as _time
        if not hasattr(self, "clustering_results") or self.clustering_results is None:
            self.clustering_results = {}
        use_gift_features = specpart_mode != "louvain_kway"
        if not use_gift_features:
            print("[SpecPart] Mode louvain_kway: running K_SpecPart without GIFT features")

        jobs = []

        # --- 1. 预处理：构建 Net 索引 (加速超边提取) ---
        _t0 = _time.time()
        print("[SpecPart] Building net index for fast subgraph extraction...")
        from collections import defaultdict
        node_to_net_names = defaultdict(list)
        parser = self.base_pipeline.parser
        
        # 简单的索引构建，只索引连接数合理的网
        for net_name, pins in parser.nets.items():
            if len(pins) > 1000: continue # 忽略全局大网
            for p in pins:
                n_nm = p['node']
                if n_nm in parser.node_name_to_idx:
                    idx = parser.node_name_to_idx[n_nm]
                    node_to_net_names[idx].append(net_name)

        print(f"[SpecPart][Timing] Net index built in {_time.time() - _t0:.1f}s")
        _t1 = _time.time()
        # --- 2. 准备任务 ---
        for cluster_id, layout_info in self.cluster_layouts.items():
            node_indices = layout_info["node_indices"]

            # Locked 处理 (保持你的逻辑)
            if layout_info.get("locked", False):
                n = len(node_indices)
                self.clustering_results[cluster_id] = {
                    "clusters": [list(node_indices)], # 修正：这里应该是 node_indices 而不是 range(n)
                    "cluster_map": {idx: 0 for idx in node_indices},
                    "num_sub_clusters": 1,
                    "locked": True
                }
                print(f"[Locked] Skip Cluster {cluster_id}")
                continue

            # 安全检查：跳过过大/过小 Cluster
            current_n = len(node_indices)
            if current_n > 5000:
                print(f"[Warning] Cluster {cluster_id} too large ({current_n}), skipping.")
                continue
            if current_n < min_cluster_size:
                continue

            # === [核心修复] 手动提取子图 (Logic Fix) ===
            # 不要使用 self.base_pipeline.clusterer.get_cluster_subgraph，因为它可能返回全图
            
            # A. 建立映射 Global -> Local
            global_to_local = {gid: i for i, gid in enumerate(node_indices)}
            
            # B. 提取 Adj (切片)
            global_adj = getattr(self.base_pipeline, 'adj_matrix', None)
            if global_adj is None and hasattr(self.base_pipeline, 'clusterer'):
                 global_adj = self.base_pipeline.clusterer.adj_mat
            
            if global_adj is not None:
                # 强制切片，确保维度是 (current_n, current_n)
                sub_adj = global_adj[node_indices, :][:, node_indices]
            else:
                continue

            # C. 提取 Hyperedges (使用索引 + ID重映射)
            sub_hyperedges = []
            candidate_nets = set()
            for gid in node_indices:
                for net in node_to_net_names.get(gid, []):
                    candidate_nets.add(net)

            for net in sorted(candidate_nets):  # sorted 确保跨运行确定性顺序
                local_hedge = []
                for p in parser.nets[net]:
                    nid = parser.node_name_to_idx.get(p['node'])
                    if nid in global_to_local:
                        local_hedge.append(global_to_local[nid])
                if len(local_hedge) >= 2:
                    sub_hyperedges.append(tuple(local_hedge))

            # D. Positions
            if "positions" in layout_info and layout_info["positions"] is not None:
                positions = layout_info["positions"]
            else:
                # Fallback extraction
                pos_list = []
                for gid in node_indices:
                    nm = parser.idx_to_node_name[gid]
                    if nm in parser.placements:
                        pos_list.append([parser.placements[nm]["x"], parser.placements[nm]["y"]])
                    else:
                        pos_list.append([0.0, 0.0])
                positions = np.array(pos_list, dtype=float)

            # 调试信息：确保 n 是小数值
            # print(f"Preparing job {cluster_id}: n={current_n}, edges={len(sub_hyperedges)}")

            # 输出目录
            c_viz = os.path.join(self.viz_dir, f"cluster_{cluster_id}")
            c_out = os.path.join(self.clustering_dir, f"cluster_{cluster_id}")
            os.makedirs(c_viz, exist_ok=True)
            os.makedirs(c_out, exist_ok=True)

            jobs.append({
                "cluster_id": cluster_id,
                "adj_matrix": sub_adj,
                "hyperedges": sub_hyperedges,
                "positions": positions,
                "node_indices": node_indices,
                "cluster_id_prefix": f"cluster_{cluster_id}",
                "ub_factor": ub_factor,
                "num_trees": num_trees,
                "best_solns": best_solns,
                "cluster_viz_dir": c_viz,
                "cluster_output_dir": c_out,
                #"base_seed": 10000,#固定specapart种子进行实验
                "base_seed": self.cluster_random_seed,
                "min_cluster_size": min_cluster_size,
            })

        # --- 3. Batch Julia execution (avoids per-cluster JIT overhead) ---
        if not jobs:
            return

        print(f"[SpecPart][Timing] Job preparation done in {_time.time() - _t1:.1f}s")
        print(f"[SpecPart] Running on {len(jobs)} clusters (num_seeds={specpart_num_seeds})...")

        use_batch = True
        try:
            # Prepare batch jobs for GIFTSpecPartPipeline.batch_recursive_bisection
            import hashlib
            batch_cluster_jobs = []
            batch_job_index = []  # maps batch index -> jobs list index

            for ji, job in enumerate(jobs):
                cluster_id = job["cluster_id"]
                base_seed = int(job.get("base_seed", 42))
                # ✅ 固定 seed = base_seed (即 cluster_random_seed)，不再加 MD5 偏移
                # 这样无论 cluster_id 如何变化，SpecPart 种子都一致
                seed = base_seed

                batch_cluster_jobs.append({
                    'hyperedges': job["hyperedges"],
                    'num_vertices': len(job["node_indices"]),
                    'node_indices': list(job["node_indices"]),
                    'random_seed': seed,
                    'num_parts': max(2, math.ceil(len(job["node_indices"]) / min_cluster_size)),
                    'positions': (job["positions"] if use_gift_features else None),
                })
                batch_job_index.append(ji)
                # ✅ DEBUG: 打印每个 cluster 传给 k_specpart 的 seed
                if ji < 5 or ji == len(jobs) - 1:
                    print(f"[DEBUG][SpecPart] cluster_id={cluster_id}, n_vertices={len(job['node_indices'])}, "
                          f"n_hyperedges={len(job['hyperedges'])}, seed={seed}, "
                          f"num_parts={max(2, math.ceil(len(job['node_indices']) / min_cluster_size))}")

            # Run clusters in parallel Julia sub-batches for speed.
            # Each sub-batch gets its own CWD to avoid file-race conditions.
            print(f"[SpecPart] Batch mode: {len(batch_cluster_jobs)} clusters in parallel Julia sub-batches")

            def _run_one_batch(batch_jobs):
                print(f"[DEBUG][K_SpecPart] Launching batch with {len(batch_jobs)} clusters, "
                      f"seeds={[j.get('random_seed','?') for j in batch_jobs[:3]]}...")
                return GIFTSpecPartPipeline.batch_k_specpart(
                    batch_jobs,
                    ub_factor=ub_factor,
                    best_solns=best_solns,
                    min_cluster_size=min_cluster_size,
                    verbose=True,
                    timeout=specpart_timeout,
                    num_workers=specpart_num_workers,
                    specpart_mode=specpart_mode,
                    per_job_timeout=specpart_per_job_timeout,
                )

            all_results_flat = [None] * len(batch_cluster_jobs)
            _t2 = _time.time()
            try:
                batch_results = _run_one_batch(batch_cluster_jobs)
                for k, res in enumerate(batch_results):
                    all_results_flat[k] = res
            except Exception as e:
                print(f"  [BatchSpecPart] Batch failed: {e}")

            # Map batch results back to clustering_results
            print(f"[SpecPart][Timing] Julia batches done in {_time.time() - _t2:.1f}s")
            _t3 = _time.time()
            done_count = 0
            diag_total_single = 0
            diag_total_multi = 0
            for bi, ji in enumerate(batch_job_index):
                job = jobs[ji]
                cluster_id = job["cluster_id"]
                node_indices = job["node_indices"]
                clusters_global = all_results_flat[bi]

                if clusters_global is None:
                    # Fallback: single cluster
                    clusters_global = [list(node_indices)]

                # Convert GLOBAL clusters -> LOCAL clusters
                g2l = {g: i for i, g in enumerate(node_indices)}
                clusters_local = []
                for cl in clusters_global:
                    loc = [g2l[g] for g in cl if g in g2l]
                    if loc:
                        clusters_local.append(loc)

                if not clusters_local:
                    clusters_local = [list(range(len(node_indices)))]

                # Build cluster_map
                cluster_map = {}
                for cid, cl in enumerate(clusters_local):
                    for v in cl:
                        cluster_map[v] = cid

                # Handle missing nodes
                n = len(node_indices)
                if len(cluster_map) < n:
                    for v in range(n):
                        if v not in cluster_map:
                            cid = len(clusters_local)
                            clusters_local.append([v])
                            cluster_map[v] = cid

                stats = {
                    "num_nodes": n,
                    "num_hyperedges": len(job["hyperedges"]),
                    "num_clusters": len(clusters_local),
                    "cluster_sizes": [len(c) for c in clusters_local],
                }

                if len(clusters_local) <= 1:
                    diag_total_single += 1
                else:
                    diag_total_multi += 1

                self.clustering_results[cluster_id] = {
                    "clusters": clusters_local,
                    "cluster_map": cluster_map,
                    "stats": stats,
                    "num_sub_clusters": len(clusters_local),
                }

                # Export results
                export_clustering_results(
                    clusters=clusters_local,
                    cluster_map=cluster_map,
                    node_indices=list(node_indices),
                    output_dir=job["cluster_output_dir"],
                    cluster_id_prefix=job["cluster_id_prefix"],
                )

                done_count += 1
                if done_count % 100 == 0 or done_count == len(batch_job_index):
                    print(f"  [SpecPart] Progress: {done_count}/{len(batch_job_index)} clusters processed")

            print(f"[SpecPart] Batch mode completed: {done_count} clusters processed")
            print(f"[SpecPart][Timing] Result mapping done in {_time.time() - _t3:.1f}s")
            print(f"[SpecPart] Summary: {diag_total_multi} clusters split, {diag_total_single} single-cluster (not split)")

            # ✅ DEBUG: 可复现性指纹 - SpecPart 结果
            import hashlib as _hl
            _sp_sizes = []
            for cid in sorted(self.clustering_results.keys()):
                cr = self.clustering_results[cid]
                _sp_sizes.append(cr.get("num_sub_clusters", 0))
            _sp_fp = _hl.md5(str(_sp_sizes).encode()).hexdigest()[:12]
            print(f"[DEBUG][Reproducibility] SpecPart results: fingerprint={_sp_fp}, "
                  f"total_sub_clusters={sum(_sp_sizes)}, num_clusters_processed={len(_sp_sizes)}")

        except Exception as e:
            print(f"[SpecPart] Batch mode failed ({e}), falling back to per-cluster mode...")
            use_batch = False

        if not use_batch:
            # Fallback: original per-cluster ProcessPoolExecutor approach
            max_workers = min(8, len(jobs))
            print(f"[SpecPart] Using {max_workers} parallel workers (per-cluster mode)")

            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                future_to_cid = {ex.submit(_cutoverlay_worker, job): job["cluster_id"] for job in jobs}

                done_count = 0
                total = len(future_to_cid)
                for fut in as_completed(future_to_cid):
                    cid = future_to_cid[fut]
                    done_count += 1
                    try:
                        ret_cid, result = fut.result(timeout=2400)

                        if result:
                            self.clustering_results[ret_cid] = result
                        else:
                            print(f"  Cluster {cid} returned no result.")

                        if done_count % 50 == 0 or done_count == total:
                            print(f"  [SpecPart] Progress: {done_count}/{total} clusters done")

                    except TimeoutError:
                        print(f"  Cluster {cid} timed out, skipping.")
                    except Exception as e:
                        print(f"  Error processing cluster {cid}: {e}")
                        import traceback
                        traceback.print_exc()
    
    def _print_summary(self):
        """打印Pipeline总结"""
        print("\n" + "=" * 80)
        print("Pipeline Summary")
        print("=" * 80)
        
        print(f"\n[1] Louvain Clustering:")
        if self.base_pipeline and self.base_pipeline.clusterer:
            print(f"    Total clusters: {len(self.base_pipeline.clusterer.clusters)}")
            print(f"    Large clusters (processed): {len(self.cluster_layouts)}")
        
        print(f"\n[2] GIFT Layout:")
        print(f"    Processed clusters: {len(self.cluster_layouts)}")
        for cluster_id, layout in self.cluster_layouts.items():
            n = len(layout['node_indices'])
            print(f"    Cluster {cluster_id}: {n} nodes")
        
        print(f"\n[3] Cut-Overlay Clustering:")
        print(f"    Processed clusters: {len(self.clustering_results)}")
        for cluster_id, result in self.clustering_results.items():
            print(f"    Cluster {cluster_id}: {result['num_sub_clusters']} sub-clusters")
        
        print(f"\n[4] Output Directories:")
        print(f"    Main output: {self.output_dir}")
        print(f"    Visualizations: {self.viz_dir}")
        print(f"    Clustering results: {self.clustering_dir}")
        
        # 显示可视化文件
        print(f"\n[5] Generated Visualizations:")
        for f in os.listdir(self.viz_dir):
            if f.endswith('.html'):
                print(f"    {os.path.join(self.viz_dir, f)}")
        
        print("\n" + "=" * 80)
        print("Pipeline completed successfully!")
        print("=" * 80)
    
    def export_full_results(self):
        """导出完整的结果摘要"""
        summary_file = os.path.join(self.output_dir, "pipeline_summary.json")
        
        summary = {
            'benchmark_dir': self.benchmark_dir,
            'louvain_clusters': len(self.cluster_layouts),
            'gift_layouts': {
                cluster_id: {
                    'num_nodes': len(layout['node_indices']),
                    'position_range': {
                        'x': [float(layout['positions'][:, 0].min()), 
                              float(layout['positions'][:, 0].max())],
                        'y': [float(layout['positions'][:, 1].min()), 
                              float(layout['positions'][:, 1].max())]
                    }
                }
                for cluster_id, layout in self.cluster_layouts.items()
            },
            'cutoverlay_clustering': {
                cluster_id: {
                    'num_sub_clusters': result['num_sub_clusters'],
                    'stats': result.get('stats', {})
                }
                for cluster_id, result in self.clustering_results.items()
            }
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\nFull summary exported to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Enhanced FPGA Clustering Pipeline with Visualization (Fixed)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 基本用法
  python main_pipeline_with_viz.py --benchmark_dir data/design --output_dir results

  # 自定义参数
  python main_pipeline_with_viz.py --benchmark_dir data/design \\
      --output_dir results --min_cluster_size 100 --resolution 1.5

  # 不运行SpecPart聚类
  python main_pipeline_with_viz.py --benchmark_dir data/design \\
      --output_dir results --no_specpart

  # 不生成GIFT可视化
  python main_pipeline_with_viz.py --benchmark_dir data/design \\
      --output_dir results --no_gift_viz
        """
    )
    
    # 输入输出
    parser.add_argument('--benchmark_dir', type=str, required=True,
                       help='FPGA benchmark directory')
    parser.add_argument('--output_dir', type=str, default='output',
                       help='Output directory (default: output)')
    parser.add_argument('--aux', type=str, default=None,
                       help='.aux file name (optional)')
    
    # Louvain参数
    parser.add_argument('--min_cluster_size', type=int, default=50,
                       help='Minimum cluster size for processing (default: 50)')
    parser.add_argument('--resolution', type=float, default=1.0,
                       help='Louvain resolution parameter (default: 1.0)')
    parser.add_argument('--max_cluster_size', type=int, default=None,
                    help='Maximum cluster size; larger clusters will be recursively split')

    # GIFT参数
    parser.add_argument('--gift_scale', type=float, default=0.5,
                       help='GIFT initial position scale (default: 0.5)')
    parser.add_argument('--use_new_filter', action='store_true',
                       help='Use Laplacian filter instead of mixed filter')
    
    # SpecPart参数
    parser.add_argument('--ub_factor', type=int, default=10,
                       help='SpecPart unbalance factor %% (default: 10)')
    parser.add_argument('--num_trees', type=int, default=5,
                       help='Number of trees for SpecPart (default: 5)')
    parser.add_argument('--best_solns', type=int, default=5,
                       help='Number of best solutions for clustering (default: 5)')
    parser.add_argument('--use_hmetis', action='store_true', help='Enable hMetis')
    parser.add_argument('--specpart_num_seeds', type=int, default=1,
                       help='Number of seeds per bisection level in SpecPart (default: 1)')
    # 可视化选项
    parser.add_argument('--show_all_arrows', action='store_true',
                       help='Show arrows for all nodes (may be dense)')
    parser.add_argument('--arrow_ratio', type=float, default=0.5,
                       help='Arrow sampling ratio when not showing all (default: 0.5)')
    parser.add_argument('--no_gift_viz', action='store_false',
                       help='Skip GIFT displacement visualization')
    parser.add_argument('--no_specpart', action='store_true',
                       help='Skip Cut-Overlay clustering')
    
    # 其他
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress detailed output')
    
    args = parser.parse_args()
    
    # 检查输入目录
    if not os.path.isdir(args.benchmark_dir):
        print(f"Error: Benchmark directory not found: {args.benchmark_dir}")
        sys.exit(1)
    
    # 运行Pipeline
    pipeline = EnhancedFPGAPipeline(args.benchmark_dir, args.output_dir)
    
    try:
        pipeline.run_full_pipeline(
            aux_file=args.aux,
            min_cluster_size=args.min_cluster_size,
            louvain_resolution=args.resolution,
            gift_scale=args.gift_scale,
            specpart_ub_factor=args.ub_factor,
            num_trees=args.num_trees,
            best_solns=args.best_solns,
            #如果要开启可视化
            #visualize_gift=not args.no_gift_viz,
            run_specpart_clustering=not args.no_specpart,
            show_all_arrows=args.show_all_arrows,
            arrow_sample_ratio=args.arrow_ratio,
            max_cluster_size=args.max_cluster_size,
            specpart_num_seeds=args.specpart_num_seeds
        )
        
        # 导出完整结果摘要
        pipeline.export_full_results()
        
    except Exception as e:
        print(f"\nError: Pipeline failed with exception:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
