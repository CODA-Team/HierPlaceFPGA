#!/usr/bin/env python3
"""
Net Re-weighting 法: 基于Clustering结果对真实网络重新赋权
==========================================================

原理:
    不创建虚拟网络，而是根据clustering结果对原有网络进行权重调整：
    - cluster内部网（同一sub-cluster）: 权重增大 → 鼓励紧凑
    - 集群内跨子集群网: 正常权重
    - 跨大集群网: 权重减小 → 允许更多自由度

优势:
    - 不改变网络结构，不引入新的约束
    - 利用DREAMPlaceFPGA原生的net weights机制
    - 更平滑的优化目标

Author: Net Re-weighting Integration Tool
"""

import os
import re
import json
import argparse
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict


class NetReweightingIntegration:
    """
    基于Clustering的网络权重调整器
    """
    
    def __init__(self, benchmark_dir: str, output_dir: str):
        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 文件路径
        self.nodes_file = None
        self.nets_file = None
        self.aux_file = None
        self.pl_file = None
        
        # 解析结果
        self.node_names = []           # 节点名称列表 (按索引)
        self.node_name_to_idx = {}     # 节点名称 -> 索引
        self.nets = {}                 # net_name -> [node_indices]
        self.net_names_ordered = []    # 保持网络顺序
        self.num_nets = 0
        self.num_pins = 0
        
        # Clustering映射
        self.node_to_louvain_cluster = {}   # node_idx -> louvain_cluster_id
        self.node_to_subcluster = {}        # node_idx -> (louvain_cluster_id, subcluster_idx)
        
    def discover_files(self) -> Dict[str, str]:
        """自动发现benchmark文件"""
        files = {}
        for f in os.listdir(self.benchmark_dir):
            full_path = os.path.join(self.benchmark_dir, f)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext == '.nodes':
                self.nodes_file = full_path
                files['nodes'] = f
            elif ext == '.nets':
                self.nets_file = full_path
                files['nets'] = f
            elif ext == '.aux':
                self.aux_file = full_path
                files['aux'] = f
            elif ext == '.pl':
                self.pl_file = full_path
                files['pl'] = f
        
        print(f"[发现文件] {files}")
        return files
    
    def parse_nodes(self) -> List[str]:
        """解析.nodes文件获取节点名称列表"""
        if not self.nodes_file:
            raise FileNotFoundError("未找到.nodes文件")
        
        self.node_names = []
        self.node_name_to_idx = {}
        
        with open(self.nodes_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('UCLA') or line.startswith('NumNodes') or line.startswith('NumTerminals'):
                    continue
                
                parts = line.split()
                if len(parts) >= 1:
                    node_name = parts[0]
                    idx = len(self.node_names)
                    self.node_names.append(node_name)
                    self.node_name_to_idx[node_name] = idx
        
        print(f"[解析节点] 共 {len(self.node_names)} 个节点")
        return self.node_names
    
    def parse_nets(self) -> Dict[str, List[int]]:
        """
        解析.nets文件，获取每个net连接的节点
        支持UCLA格式和BookShelf格式
        """
        if not self.nets_file:
            raise FileNotFoundError("未找到.nets文件")
        
        self.nets = {}
        self.net_names_ordered = []
        self.num_nets = 0
        self.num_pins = 0
        
        with open(self.nets_file, 'r') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        
        current_net_name = None
        current_net_nodes = []
        
        for line in lines:
            line_strip = line.strip()
            
            # 跳过空行和注释
            if not line_strip or line_strip.startswith('#'):
                continue
            
            # 跳过头部
            if line_strip.startswith('UCLA') or line_strip.startswith('NumNets') or line_strip.startswith('NumPins'):
                if line_strip.startswith('NumNets'):
                    match = re.search(r':\s*(\d+)', line_strip)
                    if match:
                        self.num_nets = int(match.group(1))
                elif line_strip.startswith('NumPins'):
                    match = re.search(r':\s*(\d+)', line_strip)
                    if match:
                        self.num_pins = int(match.group(1))
                continue
            
            # UCLA格式: net <name> <degree>
            if line_strip.startswith('net '):
                # 保存前一个net
                if current_net_name is not None:
                    self.nets[current_net_name] = current_net_nodes
                    self.net_names_ordered.append(current_net_name)
                
                parts = line_strip.split()
                current_net_name = parts[1] if len(parts) >= 2 else f"net_{len(self.nets)}"
                current_net_nodes = []
                continue
            
            # BookShelf格式: NetDegree : <degree> <name>
            if line_strip.startswith('NetDegree'):
                # 保存前一个net
                if current_net_name is not None:
                    self.nets[current_net_name] = current_net_nodes
                    self.net_names_ordered.append(current_net_name)
                
                parts = line_strip.split()
                current_net_name = parts[3] if len(parts) >= 4 else f"net_{len(self.nets)}"
                current_net_nodes = []
                continue
            
            # endnet (UCLA格式)
            if line_strip == 'endnet':
                if current_net_name is not None:
                    self.nets[current_net_name] = current_net_nodes
                    self.net_names_ordered.append(current_net_name)
                current_net_name = None
                current_net_nodes = []
                continue
            
            # Pin行: <node_name> <direction> [offset]
            if current_net_name is not None:
                parts = line_strip.split()
                if len(parts) >= 1:
                    node_name = parts[0]
                    if node_name in self.node_name_to_idx:
                        node_idx = self.node_name_to_idx[node_name]
                        current_net_nodes.append(node_idx)
        
        # 保存最后一个net (如果有)
        if current_net_name is not None and current_net_nodes:
            self.nets[current_net_name] = current_net_nodes
            self.net_names_ordered.append(current_net_name)
        
        if self.num_nets == 0:
            self.num_nets = len(self.nets)
        
        print(f"[解析网络] 共 {len(self.nets)} 个网络")
        return self.nets
    
    def build_clustering_maps(
        self,
        cluster_layouts: Dict,
        clustering_results: Optional[Dict] = None
    ):
        """
        构建节点到cluster的映射
        
        Args:
            cluster_layouts: Louvain cluster布局
                格式: {cluster_id: {'node_indices': [全局索引], ...}}
            clustering_results: SpecPart sub-cluster结果 (可选)
                格式: {cluster_id: {'clusters': [[局部索引], ...], ...}}
        """
        self.node_to_louvain_cluster = {}
        self.node_to_subcluster = {}
        
        for cluster_id, layout_info in cluster_layouts.items():
            global_indices = layout_info['node_indices']
            
            # 构建Louvain cluster映射
            for node_idx in global_indices:
                self.node_to_louvain_cluster[node_idx] = cluster_id
            
            # 如果有sub-cluster信息，构建更细粒度的映射
            if clustering_results and cluster_id in clustering_results:
                sub_clusters = clustering_results[cluster_id].get('clusters', [])
                for sub_idx, sub_cluster in enumerate(sub_clusters):
                    for local_idx in sub_cluster:
                        if local_idx < len(global_indices):
                            global_idx = global_indices[local_idx]
                            self.node_to_subcluster[global_idx] = (cluster_id, sub_idx)
        
        # 对于没有sub-cluster的节点，使用Louvain cluster作为sub-cluster
        for node_idx, cluster_id in self.node_to_louvain_cluster.items():
            if node_idx not in self.node_to_subcluster:
                self.node_to_subcluster[node_idx] = (cluster_id, -1)  # -1表示没有细分
        
        print(f"[构建映射] Louvain clusters: {len(set(self.node_to_louvain_cluster.values()))}")
        print(f"[构建映射] 有sub-cluster信息的节点: {sum(1 for v in self.node_to_subcluster.values() if v[1] >= 0)}")
    
    def classify_net(self, net_nodes: List[int]) -> str:
        """
        对网络进行分类
        
        Args:
            net_nodes: 网络连接的节点索引列表
            
        Returns:
            分类结果:
            - 'intra_subcluster': 所有节点在同一个sub-cluster内
            - 'intra_cluster': 节点在同一个Louvain cluster但跨sub-cluster
            - 'inter_cluster': 节点跨不同Louvain cluster
            - 'unknown': 有节点不在任何cluster中
        """
        if len(net_nodes) == 0:
            return 'unknown'
        
        # 收集所有节点的cluster信息
        louvain_clusters = set()
        subclusters = set()
        has_unknown = False
        
        for node_idx in net_nodes:
            if node_idx in self.node_to_louvain_cluster:
                louvain_clusters.add(self.node_to_louvain_cluster[node_idx])
            else:
                has_unknown = True
            
            if node_idx in self.node_to_subcluster:
                subclusters.add(self.node_to_subcluster[node_idx])
        
        # 如果有未知节点，返回unknown
        if has_unknown and len(louvain_clusters) == 0:
            return 'unknown'
        
        # 分类
        if len(louvain_clusters) > 1:
            return 'inter_cluster'
        elif len(louvain_clusters) == 1:
            # 检查是否在同一个sub-cluster
            if len(subclusters) == 1:
                return 'intra_subcluster'
            else:
                return 'intra_cluster'
        else:
            return 'unknown'
    
    def compute_net_weights(
        self,
        intra_subcluster_weight: float = 1.5,
        intra_cluster_weight: float = 1.0,
        inter_cluster_weight: float = 0.8,
        unknown_weight: float = 1.0
    ) -> Dict[str, float]:
        """
        计算每个网络的权重
        
        Args:
            intra_subcluster_weight: 同一sub-cluster内的网络权重 (>1鼓励紧凑)
            intra_cluster_weight: 同一Louvain cluster内跨sub-cluster的网络权重
            inter_cluster_weight: 跨Louvain cluster的网络权重 (<1减少约束)
            unknown_weight: 未知类型网络的权重
            
        Returns:
            net_weights: {net_name: weight}
        """
        net_weights = {}
        stats = defaultdict(int)
        
        for net_name in self.net_names_ordered:
            if net_name not in self.nets:
                continue
            
            net_nodes = self.nets[net_name]
            net_type = self.classify_net(net_nodes)
            
            if net_type == 'intra_subcluster':
                weight = intra_subcluster_weight
            elif net_type == 'intra_cluster':
                weight = intra_cluster_weight
            elif net_type == 'inter_cluster':
                weight = inter_cluster_weight
            else:
                weight = unknown_weight
            
            net_weights[net_name] = weight
            stats[net_type] += 1
        
        print(f"[网络分类统计]")
        print(f"  intra_subcluster (权重={intra_subcluster_weight}): {stats['intra_subcluster']}")
        print(f"  intra_cluster (权重={intra_cluster_weight}): {stats['intra_cluster']}")
        print(f"  inter_cluster (权重={inter_cluster_weight}): {stats['inter_cluster']}")
        print(f"  unknown (权重={unknown_weight}): {stats['unknown']}")
        
        return net_weights
    
    def write_weights_file(
        self,
        net_weights: Dict[str, float],
        output_file: Optional[str] = None
    ) -> str:
        """
        生成.wts权重文件
        
        Args:
            net_weights: {net_name: weight}
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        if output_file is None:
            original_name = os.path.basename(self.nets_file)
            base_name = os.path.splitext(original_name)[0]
            output_file = os.path.join(self.output_dir, f"{base_name}.wts")
        
        with open(output_file, 'w') as f:
            f.write("#UCLA wts 1.0\n")
            f.write(f"# Net weights based on clustering\n")
            f.write(f"# Generated by NetReweightingIntegration\n\n")
            
            for net_name in self.net_names_ordered:
                if net_name in net_weights:
                    weight = net_weights[net_name]
                    f.write(f"{net_name} {weight:.4f}\n")
        
        print(f"[写入权重文件] {output_file}")
        return output_file
    
    def copy_benchmark_files(self):
        """复制benchmark文件到输出目录"""
        files_to_copy = ['.nodes', '.nets', '.pl', '.scl', '.lib', '.aux']
        
        for f in os.listdir(self.benchmark_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in files_to_copy:
                src = os.path.join(self.benchmark_dir, f)
                dst = os.path.join(self.output_dir, f)
                if os.path.isfile(src) and not os.path.exists(dst):
                    import shutil
                    shutil.copy2(src, dst)
                    print(f"[复制文件] {f}")
    
    def update_aux_file(self, wts_file: str) -> str:
        """
        更新.aux文件以包含.wts文件
        
        Args:
            wts_file: .wts文件路径
            
        Returns:
            新.aux文件路径
        """
        if not self.aux_file:
            print("[警告] 未找到.aux文件")
            return None
        
        with open(self.aux_file, 'r') as f:
            aux_content = f.read()
        
        wts_name = os.path.basename(wts_file)
        
        # 检查是否已有wts文件引用
        if '.wts' not in aux_content:
            # 在行尾添加wts文件
            aux_content = aux_content.rstrip() + f" {wts_name}\n"
        else:
            # 替换已有的wts文件引用
            aux_content = re.sub(r'(\S+)\.wts', wts_name, aux_content)
        
        # 复制到输出目录
        original_name = os.path.basename(self.aux_file)
        output_aux = os.path.join(self.output_dir, original_name)
        
        with open(output_aux, 'w') as f:
            f.write(aux_content)
        
        print(f"[更新AUX] {output_aux}")
        return output_aux
    
    def create_dreamplace_config(self, aux_file: str, **kwargs) -> str:
        """创建DREAMPlaceFPGA配置文件"""
        config = {
            "aux_input": aux_file,
            "gpu": kwargs.get('gpu', 0),
            "num_threads": kwargs.get('num_threads', 8),
            "num_bins_x": kwargs.get('num_bins_x', 512),
            "num_bins_y": kwargs.get('num_bins_y', 512),
            "global_place_stages": [
                {
                    "num_bins_x": 512,
                    "num_bins_y": 512,
                    "iteration": kwargs.get('iteration', 2000),
                    "learning_rate": kwargs.get('learning_rate', 0.01),
                    "wirelength": kwargs.get('wirelength', 'weighted_average'),
                    "optimizer": kwargs.get('optimizer', 'nesterov')
                }
            ],
            "routability_opt_flag": kwargs.get('routability_opt_flag', 1),
            "target_density": kwargs.get('target_density', 1.0),
            "density_weight": kwargs.get('density_weight', 8e-5),
            "random_seed": kwargs.get('random_seed', 1000),
            "scale_factor": kwargs.get('scale_factor', 1.0),
            "global_place_flag": 1,
            "legalize_flag": 1,
            "detailed_place_flag": kwargs.get('detailed_place_flag', 0),
            "dtype": "float32",
            "deterministic_flag": kwargs.get('deterministic_flag', 1)
        }
        
        config_file = os.path.join(self.output_dir, "dreamplace_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"[生成配置] {config_file}")
        return config_file
    
    def run(
        self,
        cluster_layouts: Dict,
        clustering_results: Optional[Dict] = None,
        intra_subcluster_weight: float = 1.5,
        intra_cluster_weight: float = 1.0,
        inter_cluster_weight: float = 0.8,
        **dreamplace_kwargs
    ) -> Dict[str, str]:
        """
        执行完整的网络权重调整流程
        
        Args:
            cluster_layouts: Louvain cluster布局
            clustering_results: SpecPart sub-cluster结果 (可选)
            intra_subcluster_weight: 同一sub-cluster内网络权重 (建议 1.2-2.0)
            intra_cluster_weight: 同一cluster内跨sub-cluster网络权重 (建议 1.0)
            inter_cluster_weight: 跨cluster网络权重 (建议 0.5-0.9)
            **dreamplace_kwargs: DREAMPlaceFPGA配置参数
            
        Returns:
            生成的文件路径字典
        """
        print("\n" + "=" * 60)
        print("Net Re-weighting: 基于Clustering的网络权重调整")
        print("=" * 60)
        
        # Step 1: 发现和解析文件
        print("\n[Step 1] 发现和解析文件...")
        self.discover_files()
        self.parse_nodes()
        self.parse_nets()
        
        # Step 2: 构建clustering映射
        print("\n[Step 2] 构建Clustering映射...")
        self.build_clustering_maps(cluster_layouts, clustering_results)
        
        # Step 3: 计算网络权重
        print("\n[Step 3] 计算网络权重...")
        net_weights = self.compute_net_weights(
            intra_subcluster_weight=intra_subcluster_weight,
            intra_cluster_weight=intra_cluster_weight,
            inter_cluster_weight=inter_cluster_weight
        )
        
        # Step 4: 复制benchmark文件
        print("\n[Step 4] 复制benchmark文件...")
        self.copy_benchmark_files()
        
        # Step 5: 写入权重文件
        print("\n[Step 5] 写入.wts权重文件...")
        wts_file = self.write_weights_file(net_weights)
        
        # Step 6: 更新aux文件
        print("\n[Step 6] 更新.aux文件...")
        new_aux_file = self.update_aux_file(wts_file)
        
        # Step 7: 创建DREAMPlaceFPGA配置
        print("\n[Step 7] 创建DREAMPlaceFPGA配置...")
        config_file = None
        if new_aux_file:
            config_file = self.create_dreamplace_config(new_aux_file, **dreamplace_kwargs)
        
        output_files = {
            'wts': wts_file,
            'aux': new_aux_file,
            'config': config_file,
            'output_dir': self.output_dir
        }
        
        print("\n" + "=" * 60)
        print("网络权重调整完成!")
        print("=" * 60)
        print(f"\n生成的文件:")
        for key, path in output_files.items():
            if path:
                print(f"  {key}: {path}")
        
        print(f"\n运行DREAMPlaceFPGA:")
        print(f"  python dreamplacefpga/Placer.py {config_file}")
        
        return output_files


def integrate_with_pipeline(
    pipeline,
    output_dir: str,
    intra_subcluster_weight: float = 1.5,
    intra_cluster_weight: float = 1.0,
    inter_cluster_weight: float = 0.8,
    **dreamplace_kwargs
) -> Dict[str, str]:
    """
    直接与EnhancedFPGAPipeline集成
    
    Args:
        pipeline: EnhancedFPGAPipeline实例 (已运行完成)
        output_dir: 输出目录
        intra_subcluster_weight: 同一sub-cluster内网络权重
        intra_cluster_weight: 同一cluster内跨sub-cluster网络权重
        inter_cluster_weight: 跨cluster网络权重
        **dreamplace_kwargs: DREAMPlaceFPGA配置参数
    """
    integrator = NetReweightingIntegration(
        benchmark_dir=pipeline.benchmark_dir,
        output_dir=output_dir
    )
    
    return integrator.run(
        cluster_layouts=pipeline.cluster_layouts,
        clustering_results=pipeline.clustering_results,
        intra_subcluster_weight=intra_subcluster_weight,
        intra_cluster_weight=intra_cluster_weight,
        inter_cluster_weight=inter_cluster_weight,
        **dreamplace_kwargs
    )


def main():
    parser = argparse.ArgumentParser(
        description='Net Re-weighting: 基于Clustering的网络权重调整',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
权重策略说明:
  - intra_subcluster_weight: 同一sub-cluster内的网络，权重>1鼓励更紧凑
  - intra_cluster_weight: 同一Louvain cluster内跨sub-cluster的网络
  - inter_cluster_weight: 跨不同Louvain cluster的网络，权重<1减少约束

推荐配置:
  保守配置: --intra_sub 1.2 --intra 1.0 --inter 0.9
  中等配置: --intra_sub 1.5 --intra 1.0 --inter 0.8  (默认)
  激进配置: --intra_sub 2.0 --intra 1.0 --inter 0.6

示例:
  python net_reweighting_integration.py \\
      --benchmark_dir benchmarks/design1 \\
      --cluster_layouts cluster_layouts.json \\
      --clustering_results clustering_results.json \\
      --output_dir dreamplace_input \\
      --intra_sub 1.5 --intra 1.0 --inter 0.8
        """
    )
    
    parser.add_argument('--benchmark_dir', type=str, required=True,
                       help='FPGA benchmark目录')
    parser.add_argument('--cluster_layouts', type=str, required=True,
                       help='cluster_layouts的JSON文件')
    parser.add_argument('--clustering_results', type=str, default=None,
                       help='clustering_results的JSON文件 (可选)')
    parser.add_argument('--output_dir', type=str, default='dreamplace_input',
                       help='输出目录')
    
    # 权重参数
    parser.add_argument('--intra_sub', type=float, default=1.5,
                       help='同一sub-cluster内网络权重 (建议1.2-2.0)')
    parser.add_argument('--intra', type=float, default=1.0,
                       help='同一cluster内跨sub-cluster网络权重')
    parser.add_argument('--inter', type=float, default=0.8,
                       help='跨cluster网络权重 (建议0.5-0.9)')
    
    # DREAMPlaceFPGA参数
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--iteration', type=int, default=2000)
    parser.add_argument('--learning_rate', type=float, default=0.01)
    parser.add_argument('--optimizer', type=str, default='nesterov')
    
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
    
    # 运行
    integrator = NetReweightingIntegration(args.benchmark_dir, args.output_dir)
    integrator.run(
        cluster_layouts=cluster_layouts,
        clustering_results=clustering_results,
        intra_subcluster_weight=args.intra_sub,
        intra_cluster_weight=args.intra,
        inter_cluster_weight=args.inter,
        gpu=args.gpu,
        iteration=args.iteration,
        learning_rate=args.learning_rate,
        optimizer=args.optimizer
    )


if __name__ == "__main__":
    main()
