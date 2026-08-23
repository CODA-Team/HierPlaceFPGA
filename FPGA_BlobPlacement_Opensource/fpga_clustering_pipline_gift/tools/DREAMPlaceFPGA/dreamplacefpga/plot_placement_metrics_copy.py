#!/usr/bin/env python3
"""
DREAMPlaceFPGA Placement Metrics Visualization Script
======================================================

功能：
1. 解析DREAMPlaceFPGA运行日志
2. 提取 objective, HPWL, density, overflow 等指标
3. 绘制指标随迭代次数变化的曲线

使用方法：
  python plot_placement_metrics.py --log placement.log --output metrics.png
  python plot_placement_metrics.py --log placement.log --save_csv metrics.csv

Author: Anthony (Doctoral Student, SDU)
"""

import re
import os
import argparse
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


class PlacementLogParser:
    """
    DREAMPlaceFPGA日志解析器
    
    支持多种日志格式的自动检测和解析
    """
    
    def __init__(self):
        # 存储解析结果
        self.iterations = []
        self.objectives = []
        self.hpwls = []
        self.densities = []
        self.overflows = []
        
        # 额外指标
        self.wirelengths = []
        self.gradients = []
        self.learning_rates = []
        
        # 正则表达式模式（支持多种日志格式）
        self.patterns = {
            # 格式0: DREAMPlaceFPGA实际格式（最优先）
            # [INFO   ] DREAMPlaceFPGA - iter:    0, HPWL 4.654305E+05, Overflow [9.998E-01, 9.997E-01, ...], time 226.539ms
            'dreamplacefpga_actual': re.compile(
                r'iter:\s*(\d+),\s*HPWL\s+([\d.eE+-]+),\s*Overflow\s+\[([\d.eE+-]+(?:,\s*[\d.eE+-]+)*)\]',
                re.IGNORECASE
            ),
            
            # 格式1: DREAMPlace标准格式
            # Iter: 100, obj: 1.234e+06, hpwl: 1.234e+06, overflow: 0.123
            'standard': re.compile(
                r'(?:Iter(?:ation)?[\s:]*)?(\d+)[,\s]*'
                r'(?:obj(?:ective)?[\s:=]*)([\d.eE+-]+)[,\s]*'
                r'(?:hpwl[\s:=]*)([\d.eE+-]+)[,\s]*'
                r'(?:overflow[\s:=]*)([\d.eE+-]+)',
                re.IGNORECASE
            ),
            
            # 格式2: 带density
            # iteration 100: objective=1.234e+06, hpwl=1.234e+06, density=0.5, overflow=0.123
            'with_density': re.compile(
                r'(?:iter(?:ation)?[\s:]*)?(\d+)[,:\s]*'
                r'(?:obj(?:ective)?[\s:=]*)([\d.eE+-]+)[,\s]*'
                r'(?:hpwl[\s:=]*)([\d.eE+-]+)[,\s]*'
                r'(?:density[\s:=]*)([\d.eE+-]+)[,\s]*'
                r'(?:overflow[\s:=]*)([\d.eE+-]+)',
                re.IGNORECASE
            ),
            
            # 格式3: 简化格式
            # 100 1.234e+06 1.234e+06 0.123
            'simple': re.compile(
                r'^(\d+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)(?:\s+([\d.eE+-]+))?',
                re.MULTILINE
            ),
            
            # 格式4: DREAMPlaceFPGA特定格式
            # [INFO] iteration 100 hpwl 1.234e+06 overflow 0.123
            'dreamplacefpga': re.compile(
                r'\[(?:INFO|DEBUG)\].*?'
                r'(?:iter(?:ation)?[\s:]*)?(\d+).*?'
                r'hpwl[\s:=]*([\d.eE+-]+).*?'
                r'overflow[\s:=]*([\d.eE+-]+)',
                re.IGNORECASE
            ),
            
            # 格式5: 带wirelength
            'wirelength': re.compile(
                r'(?:iter(?:ation)?[\s:]*)?(\d+).*?'
                r'(?:wire(?:length)?[\s:=]*)([\d.eE+-]+)',
                re.IGNORECASE
            ),
            
            # 格式6: 单独行的指标
            'single_metric_hpwl': re.compile(
                r'(?:hpwl|wirelength)[\s:=]*([\d.eE+-]+)',
                re.IGNORECASE
            ),
            'single_metric_overflow': re.compile(
                r'overflow[\s:=]*([\d.eE+-]+)',
                re.IGNORECASE
            ),
            'single_metric_density': re.compile(
                r'density[\s:=]*([\d.eE+-]+)',
                re.IGNORECASE
            ),
            'single_metric_obj': re.compile(
                r'(?:obj(?:ective)?|loss)[\s:=]*([\d.eE+-]+)',
                re.IGNORECASE
            ),
        }
        
        # 额外存储: 多region的overflow
        self.overflow_regions = []  # List of lists
    
    def parse_log_file(self, log_file: str) -> Dict[str, List[float]]:
        """
        解析日志文件
        
        Args:
            log_file: 日志文件路径
            
        Returns:
            包含各指标列表的字典
        """
        if not os.path.exists(log_file):
            raise FileNotFoundError(f"Log file not found: {log_file}")
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 首先尝试完整格式的匹配
        self._try_parse_complete_format(content)
        
        # 如果没有解析到数据，尝试逐行解析
        if len(self.iterations) == 0:
            self._try_parse_line_by_line(content)
        
        # 返回结果
        return self._get_results()
    
    def _try_parse_complete_format(self, content: str):
        """尝试使用完整格式的正则表达式解析"""
        
        # 首先尝试DREAMPlaceFPGA实际格式（最优先）
        matches = self.patterns['dreamplacefpga_actual'].findall(content)
        if matches:
            for m in matches:
                self.iterations.append(int(m[0]))
                self.hpwls.append(float(m[1]))
                
                # 解析overflow数组
                overflow_str = m[2]
                overflow_values = [float(x.strip()) for x in overflow_str.split(',')]
                self.overflow_regions.append(overflow_values)
                
                # 取最大overflow作为主要指标（排除最后一个通常为0的值）
                valid_overflows = [v for v in overflow_values[:-1] if v > 0] or overflow_values
                self.overflows.append(max(valid_overflows) if valid_overflows else 0.0)
            return
        
        # 尝试with_density格式
        matches = self.patterns['with_density'].findall(content)
        if matches:
            for m in matches:
                self.iterations.append(int(m[0]))
                self.objectives.append(float(m[1]))
                self.hpwls.append(float(m[2]))
                self.densities.append(float(m[3]))
                self.overflows.append(float(m[4]))
            return
        
        # 尝试standard格式
        matches = self.patterns['standard'].findall(content)
        if matches:
            for m in matches:
                self.iterations.append(int(m[0]))
                self.objectives.append(float(m[1]))
                self.hpwls.append(float(m[2]))
                self.overflows.append(float(m[3]))
            return
        
        # 尝试dreamplacefpga格式
        matches = self.patterns['dreamplacefpga'].findall(content)
        if matches:
            for m in matches:
                self.iterations.append(int(m[0]))
                self.hpwls.append(float(m[1]))
                self.overflows.append(float(m[2]))
            return
        
        # 尝试simple格式
        matches = self.patterns['simple'].findall(content)
        if matches:
            for m in matches:
                self.iterations.append(int(m[0]))
                self.objectives.append(float(m[1]))
                self.hpwls.append(float(m[2]))
                self.overflows.append(float(m[3]))
                if len(m) > 4 and m[4]:
                    self.densities.append(float(m[4]))
            return
    
    def _try_parse_line_by_line(self, content: str):
        """逐行解析，提取单独的指标"""
        lines = content.split('\n')
        
        iter_count = 0
        temp_data = defaultdict(list)
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测是否是新的迭代
            iter_match = re.search(r'(?:iter(?:ation)?[\s:]*)?(\d+)', line, re.IGNORECASE)
            if iter_match:
                # 检查是否有明确的迭代标记
                if re.search(r'iter(?:ation)?', line, re.IGNORECASE):
                    iter_count = int(iter_match.group(1))
            
            # 提取各个指标
            hpwl_match = self.patterns['single_metric_hpwl'].search(line)
            if hpwl_match:
                temp_data['hpwl'].append((iter_count, float(hpwl_match.group(1))))
            
            overflow_match = self.patterns['single_metric_overflow'].search(line)
            if overflow_match:
                temp_data['overflow'].append((iter_count, float(overflow_match.group(1))))
            
            density_match = self.patterns['single_metric_density'].search(line)
            if density_match:
                temp_data['density'].append((iter_count, float(density_match.group(1))))
            
            obj_match = self.patterns['single_metric_obj'].search(line)
            if obj_match:
                temp_data['objective'].append((iter_count, float(obj_match.group(1))))
        
        # 整合数据
        if temp_data['hpwl']:
            for i, (it, val) in enumerate(temp_data['hpwl']):
                if it == 0:
                    self.iterations.append(i)
                else:
                    self.iterations.append(it)
                self.hpwls.append(val)
        
        if temp_data['overflow']:
            if len(self.overflows) == 0:
                self.overflows = [val for _, val in temp_data['overflow']]
        
        if temp_data['density']:
            if len(self.densities) == 0:
                self.densities = [val for _, val in temp_data['density']]
        
        if temp_data['objective']:
            if len(self.objectives) == 0:
                self.objectives = [val for _, val in temp_data['objective']]
    
    def _get_results(self) -> Dict[str, List[float]]:
        """获取解析结果"""
        results = {}
        
        if self.iterations:
            results['iteration'] = self.iterations
        else:
            # 如果没有显式的迭代数，生成索引
            max_len = max(
                len(self.objectives) if self.objectives else 0,
                len(self.hpwls) if self.hpwls else 0,
                len(self.overflows) if self.overflows else 0,
                len(self.densities) if self.densities else 0
            )
            if max_len > 0:
                results['iteration'] = list(range(max_len))
        
        if self.objectives:
            results['objective'] = self.objectives
        if self.hpwls:
            results['hpwl'] = self.hpwls
        if self.densities:
            results['density'] = self.densities
        if self.overflows:
            results['overflow'] = self.overflows
        
        # 添加多region overflow数据
        if self.overflow_regions:
            results['overflow_regions'] = self.overflow_regions
            # 提取各个region的overflow
            n_regions = len(self.overflow_regions[0]) if self.overflow_regions else 0
            for i in range(n_regions):
                region_values = [row[i] if i < len(row) else 0.0 for row in self.overflow_regions]
                results[f'overflow_region_{i}'] = region_values
        
        return results
    
    def parse_from_string(self, log_content: str) -> Dict[str, List[float]]:
        """直接从字符串解析"""
        self._try_parse_complete_format(log_content)
        if len(self.iterations) == 0:
            self._try_parse_line_by_line(log_content)
        return self._get_results()


class PlacementMetricsPlotter:
    """
    Placement指标可视化绘图器
    """
    
    def __init__(self, figsize: Tuple[int, int] = (14, 10)):
        self.figsize = figsize
        self.colors = {
            'objective': '#2ecc71',    # 绿色
            'hpwl': '#3498db',          # 蓝色
            'density': '#e74c3c',       # 红色
            'overflow': '#9b59b6',      # 紫色
            'overflow_region_0': '#e74c3c',   # 红色
            'overflow_region_1': '#3498db',   # 蓝色
            'overflow_region_2': '#2ecc71',   # 绿色
            'overflow_region_3': '#f39c12',   # 橙色
            'overflow_region_4': '#9b59b6',   # 紫色
        }
        self.labels = {
            'objective': 'Objective',
            'hpwl': 'HPWL (Half-Perimeter Wirelength)',
            'density': 'Density',
            'overflow': 'Overflow (Max)',
            'overflow_region_0': 'Region 0 (LUT)',
            'overflow_region_1': 'Region 1 (FF)',
            'overflow_region_2': 'Region 2 (DSP)',
            'overflow_region_3': 'Region 3 (BRAM)',
            'overflow_region_4': 'Region 4',
        }
    
    def plot_metrics(self, 
                     data: Dict[str, List[float]], 
                     output_file: str = None,
                     title: str = "DREAMPlaceFPGA Placement Metrics",
                     show_grid: bool = True,
                     log_scale: bool = False) -> plt.Figure:
        """
        绘制指标曲线
        
        Args:
            data: 解析后的数据字典
            output_file: 输出文件路径（可选）
            title: 图表标题
            show_grid: 是否显示网格
            log_scale: 是否使用对数刻度
            
        Returns:
            matplotlib Figure对象
        """
        iterations = data.get('iteration', [])
        if not iterations:
            raise ValueError("No iteration data found")
        
        # 确定要绘制的主要指标
        main_metrics = []
        for key in ['objective', 'hpwl', 'density', 'overflow']:
            if key in data and len(data[key]) > 0:
                main_metrics.append(key)
        
        # 检查是否有多region overflow数据
        has_multi_region = 'overflow_region_0' in data
        
        if not main_metrics:
            raise ValueError("No metrics data found to plot")
        
        # 创建子图布局
        if has_multi_region:
            fig = plt.figure(figsize=(14, 12))
            gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
            axes = [fig.add_subplot(gs[i, j]) for i in range(2) for j in range(2)]
        else:
            n_metrics = len(main_metrics)
            n_cols = 2
            n_rows = (n_metrics + 1) // 2
            fig, axes = plt.subplots(n_rows, n_cols, figsize=self.figsize)
            axes = axes.flatten() if n_metrics > 1 else [axes]
        
        plot_idx = 0
        
        # 绘制HPWL
        if 'hpwl' in data:
            ax = axes[plot_idx]
            values = data['hpwl']
            plot_iters = iterations[:len(values)]
            
            ax.plot(plot_iters, values, 
                   color=self.colors['hpwl'],
                   linewidth=1.5,
                   alpha=0.8)
            
            ax.set_xlabel('Iteration', fontsize=11)
            ax.set_ylabel('HPWL', fontsize=11)
            ax.set_title('HPWL vs Iteration', fontsize=12, fontweight='bold')
            
            if show_grid:
                ax.grid(True, alpha=0.3, linestyle='--')
            if log_scale:
                ax.set_yscale('log')
            
            # 统计信息
            self._add_stats(ax, values)
            plot_idx += 1
        
        # 绘制Overflow（单一或多region）
        if 'overflow' in data:
            ax = axes[plot_idx]
            
            if has_multi_region:
                # 绘制多条region曲线
                for i in range(5):
                    key = f'overflow_region_{i}'
                    if key in data and len(data[key]) > 0:
                        values = data[key]
                        # 跳过全0的region
                        if max(values) > 1e-6:
                            plot_iters = iterations[:len(values)]
                            ax.plot(plot_iters, values,
                                   color=self.colors.get(key, f'C{i}'),
                                   linewidth=1.5,
                                   alpha=0.8,
                                   label=self.labels.get(key, f'Region {i}'))
                ax.legend(loc='upper right', fontsize=9)
                ax.set_title('Overflow by Region vs Iteration', fontsize=12, fontweight='bold')
            else:
                values = data['overflow']
                plot_iters = iterations[:len(values)]
                ax.plot(plot_iters, values,
                       color=self.colors['overflow'],
                       linewidth=1.5,
                       alpha=0.8)
                ax.set_title('Overflow vs Iteration', fontsize=12, fontweight='bold')
                self._add_stats(ax, values)
            
            ax.set_xlabel('Iteration', fontsize=11)
            ax.set_ylabel('Overflow', fontsize=11)
            
            if show_grid:
                ax.grid(True, alpha=0.3, linestyle='--')
            plot_idx += 1
        
        # 绘制Objective（如果有）
        if 'objective' in data:
            ax = axes[plot_idx]
            values = data['objective']
            plot_iters = iterations[:len(values)]
            
            ax.plot(plot_iters, values,
                   color=self.colors['objective'],
                   linewidth=1.5,
                   alpha=0.8)
            
            ax.set_xlabel('Iteration', fontsize=11)
            ax.set_ylabel('Objective', fontsize=11)
            ax.set_title('Objective vs Iteration', fontsize=12, fontweight='bold')
            
            if show_grid:
                ax.grid(True, alpha=0.3, linestyle='--')
            if log_scale:
                ax.set_yscale('log')
            
            self._add_stats(ax, values)
            plot_idx += 1
        
        # 绘制Density（如果有）
        if 'density' in data:
            ax = axes[plot_idx]
            values = data['density']
            plot_iters = iterations[:len(values)]
            
            ax.plot(plot_iters, values,
                   color=self.colors['density'],
                   linewidth=1.5,
                   alpha=0.8)
            
            ax.set_xlabel('Iteration', fontsize=11)
            ax.set_ylabel('Density', fontsize=11)
            ax.set_title('Density vs Iteration', fontsize=12, fontweight='bold')
            
            if show_grid:
                ax.grid(True, alpha=0.3, linestyle='--')
            
            self._add_stats(ax, values)
            plot_idx += 1
        
        # 如果没有objective和density，添加HPWL变化率图
        if 'objective' not in data and 'density' not in data and plot_idx < len(axes):
            ax = axes[plot_idx]
            if 'hpwl' in data and len(data['hpwl']) > 1:
                hpwl_values = np.array(data['hpwl'])
                # 计算变化率 (%)
                hpwl_change = np.diff(hpwl_values) / hpwl_values[:-1] * 100
                plot_iters = iterations[1:len(hpwl_change)+1]
                
                ax.plot(plot_iters, hpwl_change,
                       color='#27ae60',
                       linewidth=1.0,
                       alpha=0.7)
                ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
                
                ax.set_xlabel('Iteration', fontsize=11)
                ax.set_ylabel('HPWL Change (%)', fontsize=11)
                ax.set_title('HPWL Change Rate vs Iteration', fontsize=12, fontweight='bold')
                
                if show_grid:
                    ax.grid(True, alpha=0.3, linestyle='--')
                plot_idx += 1
        
        # 如果还有空位，添加综合overflow图
        if plot_idx < len(axes) and 'overflow' in data:
            ax = axes[plot_idx]
            values = data['overflow']
            plot_iters = iterations[:len(values)]
            
            # 绘制overflow随迭代的变化，并标注关键点
            ax.fill_between(plot_iters, values, alpha=0.3, color=self.colors['overflow'])
            ax.plot(plot_iters, values, color=self.colors['overflow'], linewidth=1.5)
            
            # 标注最终收敛值
            if len(values) > 0:
                final_val = values[-1]
                ax.axhline(y=final_val, color='red', linestyle='--', alpha=0.5)
                ax.axhline(y=0.1, color='green', linestyle=':', alpha=0.5, label='Target (0.1)')
            
            ax.set_xlabel('Iteration', fontsize=11)
            ax.set_ylabel('Max Overflow', fontsize=11)
            ax.set_title('Overflow Convergence', fontsize=12, fontweight='bold')
            ax.legend(loc='upper right', fontsize=9)
            
            if show_grid:
                ax.grid(True, alpha=0.3, linestyle='--')
            plot_idx += 1
        
        # 隐藏未使用的子图
        for idx in range(plot_idx, len(axes)):
            axes[idx].axis('off')
        
        # 设置总标题
        fig.suptitle(title, fontsize=14, fontweight='bold')
        
        # 调整布局
        fig.subplots_adjust(top=0.92, bottom=0.08, left=0.08, right=0.95, hspace=0.35, wspace=0.25)
        
        # 保存图片
        if output_file:
            fig.savefig(output_file, dpi=150, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            print(f"[Saved] {output_file}")
        
        return fig
    
    def _add_stats(self, ax, values):
        """添加统计信息到图表"""
        if values:
            min_val = min(values)
            max_val = max(values)
            final_val = values[-1]
            
            stats_text = f'Min: {min_val:.2e}\nMax: {max_val:.2e}\nFinal: {final_val:.2e}'
            ax.text(0.98, 0.98, stats_text,
                   transform=ax.transAxes,
                   fontsize=9,
                   verticalalignment='top',
                   horizontalalignment='right',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    def plot_combined(self,
                      data: Dict[str, List[float]],
                      output_file: str = None,
                      title: str = "Placement Metrics Overview") -> plt.Figure:
        """
        在单个图中绘制所有指标（使用双Y轴）
        """
        iterations = data.get('iteration', [])
        
        fig, ax1 = plt.subplots(figsize=(12, 6))
        
        # 左Y轴：HPWL/Objective
        ax1.set_xlabel('Iteration', fontsize=12)
        ax1.set_ylabel('HPWL / Objective', color='tab:blue', fontsize=12)
        
        lines = []
        labels = []
        
        if 'hpwl' in data:
            l1, = ax1.plot(iterations[:len(data['hpwl'])], data['hpwl'],
                          color='#3498db', linewidth=1.5, label='HPWL')
            lines.append(l1)
            labels.append('HPWL')
        
        if 'objective' in data:
            l2, = ax1.plot(iterations[:len(data['objective'])], data['objective'],
                          color='#2ecc71', linewidth=1.5, linestyle='--', label='Objective')
            lines.append(l2)
            labels.append('Objective')
        
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, alpha=0.3)
        
        # 右Y轴：Overflow/Density
        ax2 = ax1.twinx()
        ax2.set_ylabel('Overflow / Density', color='tab:red', fontsize=12)
        
        if 'overflow' in data:
            l3, = ax2.plot(iterations[:len(data['overflow'])], data['overflow'],
                          color='#e74c3c', linewidth=1.5, label='Overflow')
            lines.append(l3)
            labels.append('Overflow')
        
        if 'density' in data:
            l4, = ax2.plot(iterations[:len(data['density'])], data['density'],
                          color='#9b59b6', linewidth=1.5, linestyle='-.', label='Density')
            lines.append(l4)
            labels.append('Density')
        
        ax2.tick_params(axis='y', labelcolor='tab:red')
        
        # 图例
        ax1.legend(lines, labels, loc='upper right')
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        if output_file:
            fig.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"[Saved] {output_file}")
        
        return fig


def save_to_csv(data: Dict[str, List[float]], output_file: str):
    """将数据保存为CSV文件"""
    import csv
    
    # 确定所有键
    keys = list(data.keys())
    max_len = max(len(v) for v in data.values())
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(keys)
        
        for i in range(max_len):
            row = []
            for key in keys:
                if i < len(data[key]):
                    row.append(data[key][i])
                else:
                    row.append('')
            writer.writerow(row)
    
    print(f"[Saved] {output_file}")


def generate_demo_data() -> Dict[str, List[float]]:
    """生成演示数据"""
    n_iters = 500
    iterations = list(range(n_iters))
    
    # 模拟objective的收敛
    objectives = [1e7 * np.exp(-0.005 * i) + 5e5 + np.random.randn() * 1e4 
                  for i in range(n_iters)]
    
    # 模拟HPWL
    hpwls = [8e6 * np.exp(-0.004 * i) + 2e5 + np.random.randn() * 5e3 
             for i in range(n_iters)]
    
    # 模拟density（保持相对稳定）
    densities = [0.8 + 0.1 * np.exp(-0.01 * i) + np.random.randn() * 0.01 
                 for i in range(n_iters)]
    
    # 模拟overflow的下降
    overflows = [0.5 * np.exp(-0.008 * i) + 0.01 + abs(np.random.randn()) * 0.005 
                 for i in range(n_iters)]
    
    return {
        'iteration': iterations,
        'objective': objectives,
        'hpwl': hpwls,
        'density': densities,
        'overflow': overflows
    }


def main():
    parser = argparse.ArgumentParser(
        description='DREAMPlaceFPGA Placement Metrics Visualization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 解析日志并绘图
  python plot_placement_metrics.py --log placement.log --output metrics.png
  
  # 保存数据到CSV
  python plot_placement_metrics.py --log placement.log --save_csv metrics.csv
  
  # 使用对数刻度
  python plot_placement_metrics.py --log placement.log --output metrics.png --log_scale
  
  # 生成演示图
  python plot_placement_metrics.py --demo --output demo_metrics.png

支持的日志格式:
  - DREAMPlace标准格式: Iter: 100, obj: 1.234e+06, hpwl: 1.234e+06, overflow: 0.123
  - 带density格式: iteration 100: objective=1.234e+06, hpwl=1.234e+06, density=0.5, overflow=0.123
  - 简化格式: 100 1.234e+06 1.234e+06 0.123
  - DREAMPlaceFPGA格式: [INFO] iteration 100 hpwl 1.234e+06 overflow 0.123
        """
    )
    
    parser.add_argument('--log', type=str, help='DREAMPlaceFPGA日志文件路径')
    parser.add_argument('--output', type=str, default='placement_metrics.png',
                       help='输出图片路径 (默认: placement_metrics.png)')
    parser.add_argument('--save_csv', type=str, help='保存数据到CSV文件')
    parser.add_argument('--title', type=str, default='DREAMPlaceFPGA Placement Metrics',
                       help='图表标题')
    parser.add_argument('--log_scale', action='store_true', help='使用对数刻度')
    parser.add_argument('--combined', action='store_true', help='绘制组合图（单图多指标）')
    parser.add_argument('--demo', action='store_true', help='使用演示数据')
    parser.add_argument('--no_grid', action='store_true', help='不显示网格')
    
    args = parser.parse_args()
    
    # 获取数据
    if args.demo:
        print("[Info] Using demo data...")
        data = generate_demo_data()
    elif args.log:
        print(f"[Info] Parsing log file: {args.log}")
        parser_obj = PlacementLogParser()
        data = parser_obj.parse_log_file(args.log)
    else:
        print("Error: Please specify --log <logfile> or use --demo for demo data")
        return
    
    # 打印解析结果摘要
    print("\n[Parsed Data Summary]")
    for key, values in data.items():
        if values:
            # 跳过嵌套列表
            if key == 'overflow_regions':
                print(f"  {key}: {len(values)} iterations, {len(values[0]) if values else 0} regions per iteration")
            elif isinstance(values[0], (int, float)):
                print(f"  {key}: {len(values)} points, range [{min(values):.2e}, {max(values):.2e}]")
            else:
                print(f"  {key}: {len(values)} items")
    
    # 保存CSV
    if args.save_csv:
        save_to_csv(data, args.save_csv)
    
    # 绘图
    plotter = PlacementMetricsPlotter()
    
    if args.combined:
        fig = plotter.plot_combined(data, output_file=args.output, title=args.title)
    else:
        fig = plotter.plot_metrics(
            data, 
            output_file=args.output,
            title=args.title,
            show_grid=not args.no_grid,
            log_scale=args.log_scale
        )
    
    print(f"\n[Done] Visualization saved to: {args.output}")


if __name__ == "__main__":
    main()
