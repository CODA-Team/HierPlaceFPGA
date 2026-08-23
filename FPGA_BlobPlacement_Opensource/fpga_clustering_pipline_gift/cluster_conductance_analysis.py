#!/usr/bin/env python3
"""
Cluster / Subcluster Hypergraph Density Analysis
================================================

只保留一种计算方法：

Cluster 超图连接密度 (参考 cluster placement net 构建)
-------------------------------------------------
直接复用 cluster placement 阶段的 net 构造逻辑：
- Louvain cluster 级别：每条原始 net 的 movable pin 映射到 Louvain cluster
- 涉及 >=2 个 cluster → 产生一条 cluster-level net
- 内部 net: 所有 pin 只在同一 cluster 内
- fanout: cluster 出现在多少条 cluster-level net 中

同时计算两级结果：
1. Louvain cluster 级别
2. 最终 subcluster 级别
   - 直接使用已经构建好的 subcluster / cluster placement net
   - 涉及 >=2 个 subcluster → 产生一条 subcluster-level net
   - 内部 net: 所有 pin 只在同一 subcluster 内
   - fanout: subcluster 出现在多少条 subcluster-level net 中

除上述方法外，其他 conductance / projected graph / 其它密度口径全部删除。
"""

import os
import json
import csv
import argparse
import time
from typing import Dict, List, Tuple, Set, Iterable, Optional, Any
from collections import defaultdict


# ============================================================================
# 1. Bookshelf 解析器
# ============================================================================

class BookshelfParser:
    """解析 ISPD Bookshelf 格式的 .nodes / .nets 文件"""

    def __init__(self, benchmark_dir: str):
        self.benchmark_dir = benchmark_dir
        self.node_names: List[str] = []
        self.node_name_to_idx: Dict[str, int] = {}
        self.fixed_nodes: Set[str] = set()
        self.nets: Dict[str, List[int]] = {}
        self.net_names_ordered: List[str] = []
        self._discover_and_parse()

    def _discover_and_parse(self):
        nodes_file = nets_file = None
        for f in os.listdir(self.benchmark_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext == '.nodes':
                nodes_file = os.path.join(self.benchmark_dir, f)
            elif ext == '.nets':
                nets_file = os.path.join(self.benchmark_dir, f)
        if nodes_file is None or nets_file is None:
            raise FileNotFoundError(f"Cannot find .nodes / .nets in {self.benchmark_dir}")
        self._parse_nodes(nodes_file)
        self._parse_nets(nets_file)

    def _parse_nodes(self, path: str):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('UCLA') or line.startswith('NumNodes') or line.startswith('NumTerminals'):
                    continue
                parts = line.split()
                if len(parts) >= 1:
                    name = parts[0]
                    idx = len(self.node_names)
                    self.node_names.append(name)
                    self.node_name_to_idx[name] = idx
                    if 'terminal' in line.lower() or (len(parts) >= 3 and parts[-1].upper() == 'FIXED'):
                        self.fixed_nodes.add(name)
        print(f"[Parser] {len(self.node_names)} nodes, {len(self.fixed_nodes)} fixed/terminals")

    def _parse_nets(self, path: str):
        with open(path) as f:
            content = f.read()
        lines = content.strip().split('\n')
        cur_name = None
        cur_nodes: List[int] = []

        def _save():
            nonlocal cur_name, cur_nodes
            if cur_name is not None and cur_nodes:
                self.nets[cur_name] = cur_nodes
                self.net_names_ordered.append(cur_name)
            cur_name = None
            cur_nodes = []

        for line in lines:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if s.startswith('UCLA') or s.startswith('NumNets') or s.startswith('NumPins'):
                continue
            if s.startswith('net '):
                _save()
                parts = s.split()
                cur_name = parts[1] if len(parts) >= 2 else f"net_{len(self.nets)}"
                continue
            if s.startswith('NetDegree'):
                _save()
                parts = s.split()
                cur_name = parts[3] if len(parts) >= 4 else f"net_{len(self.nets)}"
                continue
            if s == 'endnet':
                _save()
                continue
            if cur_name is not None:
                parts = s.split()
                if parts and parts[0] in self.node_name_to_idx:
                    cur_nodes.append(self.node_name_to_idx[parts[0]])
        _save()
        print(f"[Parser] {len(self.nets)} nets")

    def is_fixed(self, node_idx: int) -> bool:
        return self.node_names[node_idx] in self.fixed_nodes

    def fixed_node_indices(self) -> Set[int]:
        return {self.node_name_to_idx[n] for n in self.fixed_nodes if n in self.node_name_to_idx}


# ============================================================================
# 2. Clustering 信息加载
# ============================================================================

class ClusteringInfo:
    """从 pipeline 输出加载 clustering 信息，并按 cluster_placement_integration 的顺序构建 subcluster 映射"""

    def __init__(self, clustering_output: str, fixed_node_indices: Optional[Set[int]] = None):
        layouts_file = os.path.join(clustering_output, "cluster_layouts.json")
        results_file = os.path.join(clustering_output, "clustering_results.json")

        self.clustering_output = os.path.abspath(clustering_output)

        with open(layouts_file) as f:
            self.cluster_layouts: Dict = json.load(f)
        if os.path.exists(results_file):
            with open(results_file) as f:
                self.clustering_results: Dict = json.load(f)
        else:
            self.clustering_results = {}

        self.fixed_node_indices: Set[int] = set(fixed_node_indices or set())

        self.node_to_louvain: Dict[int, str] = {}
        self.node_to_subcluster: Dict[int, Tuple[str, int]] = {}
        self.louvain_clusters: Dict[str, List[int]] = {}
        self.subclusters: Dict[Tuple[str, int], List[int]] = {}
        self.subcluster_placement_nets: List[Tuple[Tuple[str, int], ...]] = []
        self.subcluster_placement_net_source: Optional[str] = None
        self._build_maps()
        self._extract_subcluster_placement_nets()

    def _build_maps(self):
        """
        严格对齐 cluster_placement_integration.ClusterHypergraphBuilder._build_subcluster_mapping：
        - Louvain cluster 顺序：sorted(self.cluster_layouts.items())
        - subcluster 内只保留 movable 节点（排除 fixed）
        - 若该 Louvain cluster 没有有效 subcluster，则回退到 (cid, -1)
        """
        for cid, layout in sorted(self.cluster_layouts.items(), key=lambda kv: kv[0]):
            gindices = [int(i) for i in layout['node_indices']]
            self.louvain_clusters[cid] = gindices
            for gidx in gindices:
                self.node_to_louvain[gidx] = cid

            used_explicit_subcluster = False
            if cid in self.clustering_results:
                sub_lists = self.clustering_results[cid].get('clusters', [])
                if len(sub_lists) > 0:
                    for si, local_indices in enumerate(sub_lists):
                        movable_gidxs = []
                        for lidx in local_indices:
                            if int(lidx) < len(gindices):
                                gidx = gindices[int(lidx)]
                                if gidx not in self.fixed_node_indices:
                                    movable_gidxs.append(gidx)
                        if movable_gidxs:
                            sc_key = (cid, si)
                            self.subclusters[sc_key] = movable_gidxs
                            for gidx in movable_gidxs:
                                self.node_to_subcluster[gidx] = sc_key
                            used_explicit_subcluster = True

            if used_explicit_subcluster:
                continue

            movable_gidxs = [gidx for gidx in gindices if gidx not in self.fixed_node_indices]
            if movable_gidxs:
                sc_key = (cid, -1)
                self.subclusters[sc_key] = movable_gidxs
                for gidx in movable_gidxs:
                    self.node_to_subcluster[gidx] = sc_key

        print(f"[Clustering] {len(self.louvain_clusters)} Louvain clusters, "
              f"{len(self.subclusters)} subclusters (aligned with cluster_placement_integration)")

    def _normalize_sc_key(self, obj: Any) -> Optional[Tuple[str, int]]:
        if isinstance(obj, tuple) and len(obj) == 2:
            cid, si = obj
            try:
                return str(cid), int(si)
            except Exception:
                return None
        if isinstance(obj, list) and len(obj) == 2:
            try:
                return str(obj[0]), int(obj[1])
            except Exception:
                return None
        if isinstance(obj, dict):
            cid = obj.get('cluster_id', obj.get('louvain_cluster', obj.get('parent_cluster')))
            si = obj.get('sub_index', obj.get('subcluster_index', obj.get('index')))
            if cid is not None and si is not None:
                try:
                    return str(cid), int(si)
                except Exception:
                    return None
        if isinstance(obj, str):
            if '__' in obj:
                parts = obj.rsplit('__', 1)
            elif '_' in obj:
                parts = obj.rsplit('_', 1)
            else:
                return None
            if len(parts) == 2:
                cid, si = parts
                try:
                    return str(cid), int(si)
                except Exception:
                    return None
        return None

    def _normalize_net_to_sc_tuple(self, net_obj: Any) -> Optional[Tuple[Tuple[str, int], ...]]:
        keys = (
            'subclusters', 'subcluster_ids', 'connected_subclusters',
            'pins', 'pin_subclusters', 'nodes', 'node_indices', 'movable_pins'
        )
        payload = net_obj
        if isinstance(net_obj, dict):
            payload = None
            for k in keys:
                if k in net_obj:
                    payload = net_obj[k]
                    break
            if payload is None:
                return None

        sc_set: Set[Tuple[str, int]] = set()
        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                sc_key = self._normalize_sc_key(item)
                if sc_key is not None:
                    sc_set.add(sc_key)
                    continue
                try:
                    node_idx = int(item)
                except Exception:
                    continue
                mapped = self.node_to_subcluster.get(node_idx)
                if mapped is not None:
                    sc_set.add(mapped)
        else:
            sc_key = self._normalize_sc_key(payload)
            if sc_key is not None:
                sc_set.add(sc_key)

        if not sc_set:
            return None
        return tuple(sorted(sc_set))

    def _iter_candidate_net_containers(self, obj: Any, path: str = 'root'):
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                child_path = f"{path}.{k}"
                if 'net' in lk and ('subcluster' in lk or 'placement' in lk):
                    yield child_path, v
                yield from self._iter_candidate_net_containers(v, child_path)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from self._iter_candidate_net_containers(v, f"{path}[{i}]")

    def _parse_nets_from_container(self, container: Any) -> List[Tuple[Tuple[str, int], ...]]:
        nets: List[Tuple[Tuple[str, int], ...]] = []
        if isinstance(container, dict):
            iterable = container.values()
        elif isinstance(container, list):
            iterable = container
        else:
            return nets

        for item in iterable:
            net = self._normalize_net_to_sc_tuple(item)
            if net is not None:
                nets.append(net)
        return nets


    def _default_subcluster_net_path(self) -> str:
        """
        按用户给出的 pipeline 相对位置：
          /run-*/1_clustering
            -> /run-*/2_cluster_placement/cluster_placement/cluster_design.nets
        """
        run_dir = os.path.dirname(os.path.abspath(self.clustering_output))
        return os.path.join(run_dir, '2_cluster_placement', 'cluster_placement', 'cluster_design.nets')

    def _parse_subcluster_placement_nets_file(self, path: str) -> List[Dict[str, Any]]:
        """
        解析 cluster_placement_integration 生成的 cluster_design.nets：
        - cluster_i 中的 i 对应 builder.subclusters 的顺序编号
        - fixed 节点 / DUMMY_ANCHOR 会保留为外部端点信息
        """
        idx_to_sc_key = list(sorted(self.subclusters.keys(), key=lambda x: (x[0], x[1])))
        records: List[Dict[str, Any]] = []
        cur_name = None
        cur_clusters: List[Tuple[str, int]] = []
        cur_fixed = False

        def _flush():
            nonlocal cur_name, cur_clusters, cur_fixed
            if cur_name is not None:
                uniq = tuple(sorted(set(cur_clusters)))
                records.append({
                    'net_name': cur_name,
                    'connected_subclusters': uniq,
                    'has_fixed': bool(cur_fixed),
                })
            cur_name = None
            cur_clusters = []
            cur_fixed = False

        with open(path) as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                if s.startswith('net '):
                    _flush()
                    parts = s.split()
                    cur_name = parts[1] if len(parts) >= 2 else None
                    continue
                if s == 'endnet':
                    _flush()
                    continue
                if cur_name is None:
                    continue

                parts = s.split()
                inst = parts[0]
                if inst.startswith('cluster_'):
                    try:
                        sc_idx = int(inst.replace('cluster_', '').split('_')[0])
                    except Exception:
                        continue
                    if 0 <= sc_idx < len(idx_to_sc_key):
                        cur_clusters.append(idx_to_sc_key[sc_idx])
                elif inst != 'DUMMY_ANCHOR':
                    cur_fixed = True

        _flush()
        return records

    def _extract_subcluster_placement_nets(self):
        self.clustering_output = os.path.abspath(getattr(self, 'clustering_output', '.'))

        # 1) 优先按用户指定的 pipeline 相对路径找现成的 cluster_design.nets
        explicit_net_path = self._default_subcluster_net_path()
        if os.path.exists(explicit_net_path):
            records = self._parse_subcluster_placement_nets_file(explicit_net_path)
            self.subcluster_placement_nets = records
            self.subcluster_placement_net_source = explicit_net_path
            print(f"[Clustering] subcluster placement nets: {len(records)} from {explicit_net_path}")
            return

        # 2) 退回旧的 JSON 探测（仅作为兼容）
        candidates: List[Tuple[str, List[Tuple[Tuple[str, int], ...]]]] = []
        for root_name, root_obj in (
            ('cluster_layouts', self.cluster_layouts),
            ('clustering_results', self.clustering_results),
        ):
            for path, container in self._iter_candidate_net_containers(root_obj, root_name):
                nets = self._parse_nets_from_container(container)
                if nets:
                    candidates.append((path, nets))

        if candidates:
            best_path, best_nets = max(candidates, key=lambda x: len(x[1]))
            self.subcluster_placement_nets = [
                {'net_name': f'json_net_{i}', 'connected_subclusters': net, 'has_fixed': False}
                for i, net in enumerate(best_nets)
            ]
            self.subcluster_placement_net_source = best_path
            print(f"[Clustering] subcluster placement nets: {len(best_nets)} from {best_path}")
        else:
            print('[Clustering] subcluster placement nets: NOT FOUND')


# ============================================================================
# 3. 只保留：超图连接密度分析
# ============================================================================

class HypergraphDensityAnalyzer:
    def __init__(self, parser: BookshelfParser, clustering: ClusteringInfo,
                 max_net_fanout: int = 500):
        self.parser = parser
        self.clustering = clustering
        self.max_net_fanout = max_net_fanout
        self.fixed_idx = parser.fixed_node_indices()

    def _movable_nodes(self, node_list: List[int]) -> List[int]:
        seen = set()
        movable = []
        for nidx in node_list:
            if nidx in self.fixed_idx:
                continue
            if nidx in seen:
                continue
            seen.add(nidx)
            movable.append(nidx)
        return movable

    def compute_cluster_density(self) -> Tuple[Dict[str, Dict], Dict]:
        """
        Louvain cluster 级别：
        - movable pin -> Louvain cluster
        - >=2 个 cluster: 一条 cluster-level net
        - ==1 个 cluster: 该 cluster 的内部 net
        - fanout: cluster 出现在多少条去重后的 cluster-level net 中
        """
        t0 = time.time()
        raw_hyperedges = []
        internal_count = defaultdict(int)
        skipped_small = 0
        skipped_fanout = 0
        processed_nets = 0

        for net_name in self.parser.net_names_ordered:
            movable = self._movable_nodes(self.parser.nets[net_name])
            if len(movable) < 1:
                skipped_small += 1
                continue
            if self.max_net_fanout > 0 and len(movable) > self.max_net_fanout:
                skipped_fanout += 1
                continue
            processed_nets += 1

            connected_clusters = set()
            for nidx in movable:
                cid = self.clustering.node_to_louvain.get(nidx)
                if cid is not None:
                    connected_clusters.add(cid)

            if len(connected_clusters) == 0:
                continue
            if len(connected_clusters) == 1:
                internal_count[next(iter(connected_clusters))] += 1
            else:
                raw_hyperedges.append(tuple(sorted(connected_clusters)))

        edge_weight_map = defaultdict(float)
        for hedge in raw_hyperedges:
            edge_weight_map[hedge] += 1.0

        cluster_hyperedges = list(edge_weight_map.keys())
        cluster_hyperedge_weights = list(edge_weight_map.values())

        fanout_count = defaultdict(int)
        fanout_weighted = defaultdict(float)
        for hedge, w in zip(cluster_hyperedges, cluster_hyperedge_weights):
            for cid in hedge:
                fanout_count[cid] += 1
                fanout_weighted[cid] += w

        results = {}
        for cid in sorted(self.clustering.louvain_clusters.keys()):
            internal_nets = internal_count.get(cid, 0)
            fanout = fanout_count.get(cid, 0)
            fanout_w = fanout_weighted.get(cid, 0.0)
            total_nets = internal_nets + fanout
            results[cid] = {
                'cluster_id': cid,
                'num_movable_nodes': sum(1 for g in self.clustering.louvain_clusters[cid]
                                         if not self.parser.is_fixed(g)),
                'internal_nets': internal_nets,
                'fanout': fanout,
                'fanout_weighted': fanout_w,
                'total_nets': total_nets,
                'net_density': (internal_nets / total_nets) if total_nets > 0 else 0.0,
                'net_conductance': (fanout / total_nets) if total_nets > 0 else 0.0,
                'num_subclusters': sum(1 for k in self.clustering.subclusters if k[0] == cid),
                'locked': self.clustering.cluster_layouts.get(cid, {}).get('locked', False),
            }

        summary = {
            'processed_nets': processed_nets,
            'skipped_small': skipped_small,
            'skipped_fanout': skipped_fanout,
            'num_cluster_level_nets_unique': len(cluster_hyperedges),
            'num_cluster_level_nets_raw': len(raw_hyperedges),
            'total_internal_nets': int(sum(internal_count.values())),
            'elapsed_sec': time.time() - t0,
        }
        return results, summary

    def compute_subcluster_density(self) -> Tuple[Dict[str, Dict], Dict]:
        """
        Subcluster 级别（严格参考 cluster_placement_integration.generate_cluster_nets）：
        - subcluster-level nets 直接读取 /2_cluster_placement/cluster_placement/cluster_design.nets
        - cluster_i 的 i 按 builder.subclusters 顺序映射回 (louvain_id, sub_id)
        - fixed 端点不算作内部 net，但会让对应 subcluster 记一次 fanout
        - internal net 通过对原始 net 重放 generate_cluster_nets 的映射逻辑恢复
          （因为 cluster_design.nets 本身不会写入 len(endpoints)<2 的内部 net）
        """
        t0 = time.time()
        if not self.clustering.subcluster_placement_nets:
            raise RuntimeError(
                '未找到 /2_cluster_placement/cluster_placement/cluster_design.nets，无法按要求计算 subcluster。'
            )

        source = self.clustering.subcluster_placement_net_source
        raw_hyperedges: List[Tuple[Tuple[str, int], ...]] = []
        internal_count = defaultdict(int)
        fanout_raw = defaultdict(int)
        skipped_empty = 0
        processed_nets = 0

        # A. 先从现成 cluster_design.nets 统计 subcluster-level nets / fanout
        for rec in self.clustering.subcluster_placement_nets:
            connected_subclusters = tuple(sorted(set(rec.get('connected_subclusters', ()))))
            has_fixed = bool(rec.get('has_fixed', False))
            if len(connected_subclusters) < 1:
                skipped_empty += 1
                continue
            processed_nets += 1

            if len(connected_subclusters) >= 2:
                raw_hyperedges.append(connected_subclusters)
                for sc_key in connected_subclusters:
                    fanout_raw[sc_key] += 1
            elif has_fixed:
                fanout_raw[connected_subclusters[0]] += 1

        edge_weight_map = defaultdict(float)
        for hedge in raw_hyperedges:
            edge_weight_map[hedge] += 1.0

        subcluster_hyperedges = list(edge_weight_map.keys())
        subcluster_hyperedge_weights = list(edge_weight_map.values())
        fanout_unique = defaultdict(int)
        fanout_weighted = defaultdict(float)
        for hedge, w in zip(subcluster_hyperedges, subcluster_hyperedge_weights):
            for sc_key in hedge:
                fanout_unique[sc_key] += 1
                fanout_weighted[sc_key] += w

        # B. 再按 generate_cluster_nets 的原始映射逻辑恢复内部 net（len(unique endpoints)==1 且唯一端点是 cluster_i）
        for net_name in self.parser.net_names_ordered:
            endpoints = []
            seen = set()
            for nidx in self.parser.nets[net_name]:
                node_name = self.parser.node_names[nidx]
                if self.parser.is_fixed(nidx):
                    inst = ('fixed', node_name)
                else:
                    sc_key = self.clustering.node_to_subcluster.get(nidx)
                    if sc_key is None:
                        continue
                    inst = ('subcluster', sc_key)
                if inst in seen:
                    continue
                seen.add(inst)
                endpoints.append(inst)

            if len(endpoints) == 1 and endpoints[0][0] == 'subcluster':
                internal_count[endpoints[0][1]] += 1

        results = {}
        for sc_key in sorted(self.clustering.subclusters.keys(), key=lambda x: (x[0], x[1])):
            subcluster_id = f"{sc_key[0]}_{sc_key[1]}"
            internal_nets = internal_count.get(sc_key, 0)
            fanout = fanout_raw.get(sc_key, 0)
            total_nets = internal_nets + fanout
            results[subcluster_id] = {
                'subcluster_id': subcluster_id,
                'louvain_cluster': sc_key[0],
                'sub_index': sc_key[1],
                'num_movable_nodes': len(self.clustering.subclusters[sc_key]),
                'internal_nets': internal_nets,
                'fanout': fanout,
                'fanout_unique': fanout_unique.get(sc_key, 0),
                'fanout_weighted': fanout_weighted.get(sc_key, 0.0),
                'total_nets': total_nets,
                'net_density': (internal_nets / total_nets) if total_nets > 0 else 0.0,
                'net_conductance': (fanout / total_nets) if total_nets > 0 else 0.0,
            }

        summary = {
            'processed_nets': processed_nets,
            'skipped_empty': skipped_empty,
            'subcluster_net_source': source,
            'num_subcluster_level_nets_unique': len(subcluster_hyperedges),
            'num_subcluster_level_nets_raw': len(raw_hyperedges),
            'total_internal_nets': int(sum(internal_count.values())),
            'elapsed_sec': time.time() - t0,
        }
        return results, summary

    @staticmethod
    def aggregate(items: List[Dict]) -> Dict:
        active = [x for x in items if x.get('total_nets', 0) > 0]
        if not active:
            return {
                'num_active': 0,
                'total_internal_nets': 0,
                'total_fanout': 0,
                'total_nets': 0,
                'mean_net_density': 0.0,
                'median_net_density': 0.0,
                'min_net_density': 0.0,
                'max_net_density': 0.0,
                'weighted_mean_net_density': 0.0,
                'mean_net_conductance': 0.0,
                'weighted_mean_net_conductance': 0.0,
            }

        total_nets = sum(x['total_nets'] for x in active)
        return {
            'num_active': len(active),
            'total_internal_nets': int(sum(x['internal_nets'] for x in active)),
            'total_fanout': int(sum(x['fanout'] for x in active)),
            'total_nets': int(total_nets),
            'mean_net_density': sum(x['net_density'] for x in active) / len(active),
            'median_net_density': sorted(x['net_density'] for x in active)[len(active) // 2],
            'min_net_density': min(x['net_density'] for x in active),
            'max_net_density': max(x['net_density'] for x in active),
            'weighted_mean_net_density': (
                sum(x['net_density'] * x['total_nets'] for x in active) / total_nets
                if total_nets > 0 else 0.0
            ),
            'mean_net_conductance': sum(x['net_conductance'] for x in active) / len(active),
            'weighted_mean_net_conductance': (
                sum(x['net_conductance'] * x['total_nets'] for x in active) / total_nets
                if total_nets > 0 else 0.0
            ),
        }

    def generate_report(self) -> Dict:
        cluster_map, cluster_summary = self.compute_cluster_density()
        subcluster_map, subcluster_summary = self.compute_subcluster_density()

        per_cluster = [cluster_map[cid] for cid in sorted(cluster_map.keys())]
        per_subcluster = [subcluster_map[sid] for sid in sorted(
            subcluster_map.keys(),
            key=lambda x: (subcluster_map[x]['louvain_cluster'], subcluster_map[x]['sub_index'])
        )]

        return {
            'method': {
                'name': 'cluster_hypergraph_density',
                'description': '只保留 cluster placement net 构造逻辑对应的超图连接密度',
                'max_net_fanout': self.max_net_fanout,
            },
            'cluster_summary': cluster_summary,
            'cluster_aggregate': self.aggregate(per_cluster),
            'subcluster_summary': subcluster_summary,
            'subcluster_aggregate': self.aggregate(per_subcluster),
            'per_cluster': per_cluster,
            'per_subcluster': per_subcluster,
        }


# ============================================================================
# 4. 输出
# ============================================================================


def print_report(report: Dict, top_k: int = 30):
    print("\n" + "=" * 80)
    print("  CLUSTER / SUBCLUSTER 超图连接密度报告")
    print("=" * 80)

    method = report['method']
    print(f"\n方法: {method['name']}")
    print("说明: 只使用 cluster placement 阶段的 net 构造逻辑，不再输出 conductance / 投影图等其它口径。")
    print(f"max_net_fanout: {method['max_net_fanout']}")

    cs = report['cluster_summary']
    ca = report['cluster_aggregate']
    print("\n" + "─" * 64)
    print("一、Louvain Cluster 级别")
    print("─" * 64)
    print(f"处理 net 数:                  {cs['processed_nets']}")
    print(f"跳过 net (movable<1):         {cs['skipped_small']}")
    print(f"跳过 net (fanout过大):        {cs['skipped_fanout']}")
    print(f"cluster-level net 数(去重):   {cs['num_cluster_level_nets_unique']}")
    print(f"cluster-level net 数(含重):   {cs['num_cluster_level_nets_raw']}")
    print(f"内部 net 总数:                {cs['total_internal_nets']}")
    print(f"有效 cluster 数:              {ca['num_active']}")
    print(f"平均 net_density:             {ca['mean_net_density']:.6f}")
    print(f"加权平均 net_density:         {ca['weighted_mean_net_density']:.6f}")
    print(f"平均 net_conductance:         {ca['mean_net_conductance']:.6f}")
    print(f"加权平均 net_conductance:     {ca['weighted_mean_net_conductance']:.6f}")

    ss = report['subcluster_summary']
    sa = report['subcluster_aggregate']
    print("\n" + "─" * 64)
    print("二、Subcluster 级别")
    print("─" * 64)
    print("说明: 直接使用已构建好的 subcluster placement nets。")
    print(f"处理 net 数:                  {ss['processed_nets']}")
    print(f"跳过空 net:                  {ss['skipped_empty']}")
    print(f"subcluster net 来源:          {ss['subcluster_net_source']}")
    print(f"subcluster-level net 数(去重):{ss['num_subcluster_level_nets_unique']}")
    print(f"subcluster-level net 数(含重):{ss['num_subcluster_level_nets_raw']}")
    print(f"内部 net 总数:                {ss['total_internal_nets']}")
    print(f"有效 subcluster 数:           {sa['num_active']}")
    print(f"平均 net_density:             {sa['mean_net_density']:.6f}")
    print(f"加权平均 net_density:         {sa['weighted_mean_net_density']:.6f}")
    print(f"平均 net_conductance:         {sa['mean_net_conductance']:.6f}")
    print(f"加权平均 net_conductance:     {sa['weighted_mean_net_conductance']:.6f}")

    print("\n" + "─" * 110)
    print(f"三、Cluster 详情（按 net_density 从高到低，前 {top_k} 个）")
    print("─" * 110)
    print(f"  {'Cluster':>12s}  {'节点数':>8s}  {'内部net':>10s}  {'fanout':>8s}  {'总net':>8s}  {'density':>10s}  {'conduct':>10s}  {'子簇数':>8s}  {'锁定':>4s}")
    print(f"  {'─'*12}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*4}")
    for c in sorted(report['per_cluster'], key=lambda x: (-x['net_density'], x['cluster_id']))[:top_k]:
        print(f"  {c['cluster_id']:>12s}  {c['num_movable_nodes']:>8d}  {c['internal_nets']:>10d}  {c['fanout']:>8d}  {c['total_nets']:>8d}  {c['net_density']:>10.6f}  {c['net_conductance']:>10.6f}  {c['num_subclusters']:>8d}  {('Y' if c['locked'] else ''):>4s}")

    print("\n" + "─" * 122)
    print(f"四、Subcluster 详情（按 net_density 从高到低，前 {top_k} 个）")
    print("─" * 122)
    print(f"  {'Subcluster':>18s}  {'Cluster':>12s}  {'sub_idx':>7s}  {'节点数':>8s}  {'内部net':>10s}  {'fanout':>8s}  {'总net':>8s}  {'density':>10s}  {'conduct':>10s}")
    print(f"  {'─'*18}  {'─'*12}  {'─'*7}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*10}")
    for s in sorted(report['per_subcluster'], key=lambda x: (-x['net_density'], x['subcluster_id']))[:top_k]:
        print(f"  {s['subcluster_id']:>18s}  {s['louvain_cluster']:>12s}  {s['sub_index']:>7d}  {s['num_movable_nodes']:>8d}  {s['internal_nets']:>10d}  {s['fanout']:>8d}  {s['total_nets']:>8d}  {s['net_density']:>10.6f}  {s['net_conductance']:>10.6f}")


def save_cluster_csv(report: Dict, path: str):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'cluster_id', 'num_movable_nodes',
            'internal_nets', 'fanout', 'fanout_weighted', 'total_nets',
            'net_density', 'net_conductance', 'num_subclusters', 'locked'
        ])
        for c in report['per_cluster']:
            w.writerow([
                c['cluster_id'], c['num_movable_nodes'],
                c['internal_nets'], c['fanout'], f"{c['fanout_weighted']:.4f}", c['total_nets'],
                f"{c['net_density']:.8f}", f"{c['net_conductance']:.8f}",
                c['num_subclusters'], c['locked']
            ])
    print(f"[输出] Cluster CSV -> {path}")


def save_subcluster_csv(report: Dict, path: str):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'subcluster_id', 'louvain_cluster', 'sub_index', 'num_movable_nodes',
            'internal_nets', 'fanout', 'fanout_weighted', 'total_nets',
            'net_density', 'net_conductance'
        ])
        for s in report['per_subcluster']:
            w.writerow([
                s['subcluster_id'], s['louvain_cluster'], s['sub_index'], s['num_movable_nodes'],
                s['internal_nets'], s['fanout'], f"{s['fanout_weighted']:.4f}", s['total_nets'],
                f"{s['net_density']:.8f}", f"{s['net_conductance']:.8f}"
            ])
    print(f"[输出] Subcluster CSV -> {path}")


# ============================================================================
# 5. Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description='Cluster / Subcluster Hypergraph Density Analysis (only one method kept)'
    )
    parser.add_argument('--benchmark_dir', type=str, required=True,
                        help='ISPD benchmark 目录 (含 .nodes, .nets)')
    parser.add_argument('--clustering_output', type=str, default=None,
                        help='Pipeline Phase 1 输出目录 (含 cluster_layouts.json / clustering_results.json)')
    parser.add_argument('--cluster_layouts', type=str, default=None,
                        help='直接指定 cluster_layouts.json 路径')
    parser.add_argument('--clustering_results', type=str, default=None,
                        help='直接指定 clustering_results.json 路径')
    parser.add_argument('--output_dir', type=str, default='hypergraph_density_analysis',
                        help='输出目录')
    parser.add_argument('--max_net_fanout', type=int, default=500,
                        help='跳过 movable pin > 此阈值的 net (0=不过滤)')
    parser.add_argument('--top_k', type=int, default=30,
                        help='终端打印 top-K')
    args = parser.parse_args()

    if args.clustering_output:
        clustering_dir = args.clustering_output
    elif args.cluster_layouts:
        clustering_dir = os.path.dirname(args.cluster_layouts)
    else:
        raise ValueError('请指定 --clustering_output 或 --cluster_layouts')

    if args.cluster_layouts and args.clustering_output is None:
        import tempfile, shutil
        tmp_dir = tempfile.mkdtemp(prefix='hypergraph_density_tmp_')
        shutil.copy2(args.cluster_layouts, os.path.join(tmp_dir, 'cluster_layouts.json'))
        if args.clustering_results and os.path.exists(args.clustering_results):
            shutil.copy2(args.clustering_results, os.path.join(tmp_dir, 'clustering_results.json'))
        else:
            with open(os.path.join(tmp_dir, 'clustering_results.json'), 'w') as f:
                json.dump({}, f)
        clustering_dir = tmp_dir

    os.makedirs(args.output_dir, exist_ok=True)

    print('=' * 80)
    print('  CLUSTER / SUBCLUSTER HYPERGRAPH DENSITY ANALYSIS')
    print('=' * 80)
    print(f'  Benchmark:       {args.benchmark_dir}')
    print(f'  Clustering:      {clustering_dir}')
    print(f'  Max net fanout:  {args.max_net_fanout}')
    print()

    bp = BookshelfParser(args.benchmark_dir)
    ci = ClusteringInfo(clustering_dir, fixed_node_indices=bp.fixed_node_indices())
    analyzer = HypergraphDensityAnalyzer(bp, ci, max_net_fanout=args.max_net_fanout)
    report = analyzer.generate_report()

    print_report(report, top_k=args.top_k)

    json_path = os.path.join(args.output_dir, 'hypergraph_density_report.json')
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f'[输出] 完整报告 -> {json_path}')

    save_cluster_csv(report, os.path.join(args.output_dir, 'cluster_hypergraph_density_summary.csv'))
    save_subcluster_csv(report, os.path.join(args.output_dir, 'subcluster_hypergraph_density_summary.csv'))

    print(f"\n所有输出已保存到: {args.output_dir}/")


if __name__ == '__main__':
    main()
