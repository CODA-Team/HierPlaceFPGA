
#!/usr/bin/env python3
"""
FPGA Visualization Integration Module (Fixed Version)
======================================================

与现有FPGA Pipeline完整整合的可视化模块

功能:
1. 固定节点着重显示（红色菱形）
2. IO节点显示（绿色方块）
3. IO站点显示（从.scl文件解析）
4. 点击节点查看连接关系
5. GIFT位移可视化
6. 节点搜索功能
7. 显示控制选项

修复说明:
- 确保邻接矩阵、固定节点、IO节点、IO站点信息正确传递
- 支持从parser获取完整的节点类型信息
"""

import os
import json
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set, Any
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.csgraph import minimum_spanning_tree
import colorsys
import sys as _sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in _sys.path:
    _sys.path.insert(0, _THIS_DIR)

from gift_specpart_complete import GIFTSpecPartPipeline

# ============================================================================
# SCL Parser - 解析IO站点位置
# ============================================================================

class SCLParser:
    """解析.scl文件，提取IO站点位置"""
    
    def __init__(self):
        self.sites = {}
        self.resources = {}
        self.sitemap = []
        self.chip_width = 0
        self.chip_height = 0
        self.io_locations = []
        
    def parse(self, scl_file: str) -> Dict:
        """解析.scl文件"""
        current_section = None
        current_site = None
        
        with open(scl_file, 'r') as f:
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
                        x, y, site_type = int(parts[0]), int(parts[1]), parts[2]
                        self.sitemap.append((x, y, site_type))
                        if site_type == 'IO':
                            self.io_locations.append((x, y))
        
        return {
            'sites': self.sites,
            'resources': self.resources,
            'sitemap': self.sitemap,
            'chip_width': self.chip_width,
            'chip_height': self.chip_height,
            'io_locations': self.io_locations
        }
    
    def get_io_positions(self) -> Optional[np.ndarray]:
        """获取IO位置数组"""
        if not self.io_locations:
            return None
        return np.array(self.io_locations, dtype=float)


# ============================================================================
# HTML Generator - 生成交互式HTML
# ============================================================================

def generate_interactive_html(
    positions: np.ndarray,
    adj_matrix = None,
    node_names: Optional[List[str]] = None,
    node_types: Optional[Dict[int, Any]] = None,
    fixed_nodes: Optional[Set[int]] = None,
    io_nodes: Optional[Set[int]] = None,
    init_positions: Optional[np.ndarray] = None,
    io_site_positions: Optional[np.ndarray] = None,
    hyperedges: Optional[List[Tuple]] = None,
    title: str = "FPGA Interactive Visualization",
    output_path: str = "fpga_interactive.html"
) -> str:
    """
    生成交互式HTML可视化
    
    Args:
        positions: 节点最终位置 (n, 2)
        adj_matrix: 邻接矩阵 (scipy sparse)
        node_names: 节点名称
        node_types: 节点类型信息
        fixed_nodes: 固定节点集合
        io_nodes: IO节点集合
        init_positions: 初始位置（用于GIFT位移）
        io_site_positions: IO站点位置
        hyperedges: 超边列表
        title: 标题
        output_path: 输出路径
        
    Returns:
        输出文件路径
    """
    n = len(positions)
    
    if node_names is None:
        node_names = [f"node_{i}" for i in range(n)]
    if node_types is None:
        node_types = {}
    fixed_nodes = fixed_nodes or set()
    io_nodes = io_nodes or set()
    
    # 构建连接信息
    connections = defaultdict(set)
    edges = []
    
    if adj_matrix is not None:
        cx = adj_matrix.tocoo()
        for i, j, v in zip(cx.row, cx.col, cx.data):
            if i < j and v > 0:
                connections[int(i)].add(int(j))
                connections[int(j)].add(int(i))
                edges.append([int(i), int(j)])
    
    if hyperedges:
        for hedge in hyperedges:
            for i in range(len(hedge)):
                for j in range(i + 1, len(hedge)):
                    connections[int(hedge[i])].add(int(hedge[j]))
                    connections[int(hedge[j])].add(int(hedge[i]))
    
    # 准备节点数据
    nodes_data = []
    for i in range(n):
        node_info = node_types.get(i, {})
        if isinstance(node_info, dict):
            cell_type = node_info.get('cell_type', 'unknown')
        else:
            cell_type = str(node_info)
            
        node_data = {
            'id': i,
            'name': node_names[i],
            'x': float(positions[i, 0]),
            'y': float(positions[i, 1]),
            'type': cell_type,
            'is_fixed': i in fixed_nodes,
            'is_io': i in io_nodes,
            'connections': [int(c) for c in connections.get(i, [])]
        }
        
        if init_positions is not None:
            node_data['init_x'] = float(init_positions[i, 0])
            node_data['init_y'] = float(init_positions[i, 1])
            node_data['displacement'] = float(np.linalg.norm(
                positions[i] - init_positions[i]
            ))
        
        nodes_data.append(node_data)
    
    # IO站点数据
    io_sites_data = []
    if io_site_positions is not None:
        for x, y in io_site_positions:
            io_sites_data.append({'x': float(x), 'y': float(y)})
    
    # 生成HTML
    html_content = _generate_html_template(
        title=title,
        nodes_data=nodes_data,
        edges_data=edges,
        io_sites_data=io_sites_data,
        has_init_positions=init_positions is not None
    )
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"  Interactive visualization saved: {output_path}")
    return output_path


def _generate_html_template(
    title: str,
    nodes_data: List[dict],
    edges_data: List[List[int]],
    io_sites_data: List[dict],
    has_init_positions: bool
) -> str:
    """生成HTML模板"""
    
    # 统计信息
    n_fixed = sum(1 for n in nodes_data if n['is_fixed'])
    n_io = sum(1 for n in nodes_data if n['is_io'])
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #ecf0f1;
            min-height: 100vh;
        }}
        
        .header {{
            background: rgba(0, 0, 0, 0.4);
            padding: 16px 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .header h1 {{
            font-size: 22px;
            font-weight: 600;
            background: linear-gradient(90deg, #4A90D9, #9B59B6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .container {{ display: flex; height: calc(100vh - 64px); }}
        
        .main-plot {{ flex: 1; padding: 16px; }}
        
        #plot {{
            width: 100%;
            height: 100%;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}
        
        .sidebar {{
            width: 320px;
            background: rgba(0, 0, 0, 0.4);
            border-left: 1px solid rgba(255, 255, 255, 0.1);
            padding: 16px;
            overflow-y: auto;
        }}
        
        .panel {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 14px;
        }}
        
        .panel h3 {{
            font-size: 12px;
            font-weight: 600;
            color: #9B59B6;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 6px 0;
            font-size: 12px;
        }}
        
        .legend-symbol {{
            width: 14px;
            height: 14px;
            margin-right: 8px;
        }}
        
        .legend-symbol.circle {{ border-radius: 50%; }}
        .legend-symbol.diamond {{
            transform: rotate(45deg);
            width: 10px; height: 10px;
            margin: 2px 10px 2px 2px;
        }}
        .legend-symbol.square {{ border-radius: 2px; }}
        
        .checkbox-group {{
            display: flex;
            align-items: center;
            margin: 6px 0;
        }}
        
        .checkbox-group input {{ margin-right: 8px; cursor: pointer; }}
        .checkbox-group span {{ font-size: 12px; }}
        
        .node-info {{ display: none; }}
        .node-info.active {{ display: block; }}
        
        .node-info h4 {{
            color: #F39C12;
            font-size: 15px;
            margin-bottom: 10px;
            word-break: break-all;
        }}
        
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            font-size: 12px;
        }}
        
        .info-row .label {{ color: #888; }}
        .info-row .value {{ color: #ecf0f1; font-weight: 500; }}
        
        .connected-list {{
            margin-top: 10px;
            max-height: 180px;
            overflow-y: auto;
        }}
        
        .connected-list h5 {{
            font-size: 11px;
            color: #9B59B6;
            margin-bottom: 6px;
        }}
        
        .connected-node {{
            display: inline-block;
            background: rgba(155, 89, 182, 0.25);
            padding: 3px 6px;
            border-radius: 3px;
            margin: 2px;
            font-size: 10px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        
        .connected-node:hover {{ background: rgba(155, 89, 182, 0.45); }}
        
        .stats {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}
        
        .stat-item {{
            background: rgba(0, 0, 0, 0.3);
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 18px;
            font-weight: 700;
            color: #4A90D9;
        }}
        
        .stat-label {{
            font-size: 10px;
            color: #888;
            margin-top: 2px;
        }}
        
        .btn {{
            background: linear-gradient(135deg, #4A90D9, #357ABD);
            border: none;
            color: white;
            padding: 8px 14px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            width: 100%;
            margin-top: 6px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(74, 144, 217, 0.4);
        }}
        
        .btn.secondary {{ background: rgba(255, 255, 255, 0.1); }}
        
        .search-input {{
            width: 100%;
            padding: 8px 10px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 5px;
            color: #ecf0f1;
            font-size: 12px;
        }}
        
        .search-input:focus {{
            outline: none;
            border-color: #4A90D9;
        }}
        
        .status {{
            font-size: 11px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <span class="status" id="status">Click on a node to see its connections</span>
    </div>
    
    <div class="container">
        <div class="main-plot">
            <div id="plot"></div>
        </div>
        
        <div class="sidebar">
            <div class="panel">
                <h3>Statistics</h3>
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-value" id="total-nodes">0</div>
                        <div class="stat-label">Total Nodes</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="fixed-count">0</div>
                        <div class="stat-label">Fixed</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="io-count">0</div>
                        <div class="stat-label">IO</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="edge-count">0</div>
                        <div class="stat-label">Edges</div>
                    </div>
                </div>
            </div>
            
            <div class="panel">
                <h3>Legend</h3>
                <div class="legend-item">
                    <div class="legend-symbol circle" style="background: #4A90D9;"></div>
                    <span>Normal Node</span>
                </div>
                <div class="legend-item">
                    <div class="legend-symbol diamond" style="background: #E74C3C;"></div>
                    <span>Fixed Node ({n_fixed})</span>
                </div>
                <div class="legend-item">
                    <div class="legend-symbol square" style="background: #2ECC71;"></div>
                    <span>IO Node ({n_io})</span>
                </div>
                <div class="legend-item">
                    <div class="legend-symbol square" style="background: transparent; border: 2px solid #27AE60;"></div>
                    <span>IO Site ({len(io_sites_data)})</span>
                </div>
                <div class="legend-item">
                    <div class="legend-symbol circle" style="background: #F39C12;"></div>
                    <span>Selected Node</span>
                </div>
                <div class="legend-item">
                    <div class="legend-symbol circle" style="background: #9B59B6;"></div>
                    <span>Connected Node</span>
                </div>
            </div>
            
            <div class="panel">
                <h3>Display Options</h3>
                <div class="checkbox-group">
                    <input type="checkbox" id="show-edges" checked>
                    <span>Show Edges ({len(edges_data)})</span>
                </div>
                <div class="checkbox-group">
                    <input type="checkbox" id="show-io-sites" checked>
                    <span>Show IO Sites</span>
                </div>
                {"<div class='checkbox-group'><input type='checkbox' id='show-displacement'><span>Show GIFT Displacement</span></div>" if has_init_positions else ""}
                <div class="checkbox-group">
                    <input type="checkbox" id="highlight-fixed">
                    <span>Highlight Fixed Nodes</span>
                </div>
                <div class="checkbox-group">
                    <input type="checkbox" id="highlight-io">
                    <span>Highlight IO Nodes</span>
                </div>
            </div>
            
            <div class="panel">
                <h3>Search Node</h3>
                <input type="text" class="search-input" id="search-input" placeholder="Enter node name or index...">
                <button class="btn" onclick="searchNode()">Search</button>
            </div>
            
            <div class="panel node-info" id="node-info">
                <h3>Selected Node</h3>
                <h4 id="selected-name">-</h4>
                <div class="info-row">
                    <span class="label">Index</span>
                    <span class="value" id="selected-index">-</span>
                </div>
                <div class="info-row">
                    <span class="label">Type</span>
                    <span class="value" id="selected-type">-</span>
                </div>
                <div class="info-row">
                    <span class="label">Position</span>
                    <span class="value" id="selected-position">-</span>
                </div>
                <div class="info-row">
                    <span class="label">Status</span>
                    <span class="value" id="selected-status">-</span>
                </div>
                <div class="info-row">
                    <span class="label">Connections</span>
                    <span class="value" id="selected-connections">-</span>
                </div>
                {"<div class='info-row'><span class='label'>Displacement</span><span class='value' id='selected-displacement'>-</span></div>" if has_init_positions else ""}
                
                <div class="connected-list">
                    <h5>Connected Nodes (click to navigate):</h5>
                    <div id="connected-nodes"></div>
                </div>
                
                <button class="btn secondary" onclick="clearSelection()">Clear Selection</button>
            </div>
        </div>
    </div>

    <script>
        const nodesData = {json.dumps(nodes_data)};
        const edgesData = {json.dumps(edges_data)};
        const ioSitesData = {json.dumps(io_sites_data)};
        const hasInitPositions = {'true' if has_init_positions else 'false'};
        
        let selectedNodeIndex = null;
        let baseTraceCount = 0;
        
        const colors = {{
            normal: '#4A90D9',
            fixed: '#E74C3C',
            io: '#2ECC71',
            ioSite: '#27AE60',
            selected: '#F39C12',
            connected: '#9B59B6',
            edge: 'rgba(150, 150, 150, 0.15)',
            connectedEdge: 'rgba(155, 89, 182, 0.8)'
        }};
        
        function init() {{
            document.getElementById('total-nodes').textContent = nodesData.length;
            document.getElementById('fixed-count').textContent = nodesData.filter(n => n.is_fixed).length;
            document.getElementById('io-count').textContent = nodesData.filter(n => n.is_io).length;
            document.getElementById('edge-count').textContent = edgesData.length;
            createPlot();
            setupEventListeners();
        }}
        
        function createPlot() {{
            const traces = [];
            
            // IO Sites
            if (ioSitesData.length > 0) {{
                traces.push({{
                    x: ioSitesData.map(s => s.x),
                    y: ioSitesData.map(s => s.y),
                    mode: 'markers',
                    type: 'scatter',
                    name: 'IO Sites',
                    marker: {{
                        size: 10,
                        color: 'transparent',
                        symbol: 'square',
                        line: {{ width: 2, color: colors.ioSite }}
                    }},
                    hoverinfo: 'text',
                    hovertext: ioSitesData.map((s, i) => `IO Site<br>(${{s.x.toFixed(0)}}, ${{s.y.toFixed(0)}})`)
                }});
            }}
            
            // Edges
            const edgeX = [], edgeY = [];
            edgesData.forEach(([i, j]) => {{
                edgeX.push(nodesData[i].x, nodesData[j].x, null);
                edgeY.push(nodesData[i].y, nodesData[j].y, null);
            }});
            
            traces.push({{
                x: edgeX,
                y: edgeY,
                mode: 'lines',
                type: 'scatter',
                name: 'Edges',
                line: {{ width: 0.5, color: colors.edge }},
                hoverinfo: 'none'
            }});
            
            // Normal nodes
            const normalNodes = nodesData.filter(n => !n.is_fixed && !n.is_io);
            if (normalNodes.length > 0) {{
                traces.push({{
                    x: normalNodes.map(n => n.x),
                    y: normalNodes.map(n => n.y),
                    mode: 'markers',
                    type: 'scatter',
                    name: 'Normal',
                    marker: {{ size: 5, color: colors.normal, symbol: 'circle' }},
                    customdata: normalNodes.map(n => n.id),
                    hoverinfo: 'text',
                    hovertext: normalNodes.map(n => getHoverText(n))
                }});
            }}
            
            // IO nodes
            const ioNodes = nodesData.filter(n => n.is_io);
            if (ioNodes.length > 0) {{
                traces.push({{
                    x: ioNodes.map(n => n.x),
                    y: ioNodes.map(n => n.y),
                    mode: 'markers',
                    type: 'scatter',
                    name: 'IO',
                    marker: {{ size: 9, color: colors.io, symbol: 'square', line: {{ width: 1, color: 'white' }} }},
                    customdata: ioNodes.map(n => n.id),
                    hoverinfo: 'text',
                    hovertext: ioNodes.map(n => getHoverText(n))
                }});
            }}
            
            // Fixed nodes
            const fixedNodes = nodesData.filter(n => n.is_fixed);
            if (fixedNodes.length > 0) {{
                traces.push({{
                    x: fixedNodes.map(n => n.x),
                    y: fixedNodes.map(n => n.y),
                    mode: 'markers',
                    type: 'scatter',
                    name: 'Fixed',
                    marker: {{ size: 11, color: colors.fixed, symbol: 'diamond', line: {{ width: 1, color: 'white' }} }},
                    customdata: fixedNodes.map(n => n.id),
                    hoverinfo: 'text',
                    hovertext: fixedNodes.map(n => getHoverText(n))
                }});
            }}
            
            baseTraceCount = traces.length;
            
            const layout = {{
                plot_bgcolor: '#1a1a2e',
                paper_bgcolor: '#1a1a2e',
                font: {{ color: '#ecf0f1' }},
                showlegend: false,
                xaxis: {{ title: 'X', gridcolor: '#2d2d44', zerolinecolor: '#2d2d44' }},
                yaxis: {{ title: 'Y', gridcolor: '#2d2d44', zerolinecolor: '#2d2d44', scaleanchor: 'x', scaleratio: 1 }},
                hovermode: 'closest',
                dragmode: 'pan',
                margin: {{ l: 50, r: 10, t: 10, b: 50 }}
            }};
            
            Plotly.newPlot('plot', traces, layout, {{ responsive: true, scrollZoom: true }});
            
            document.getElementById('plot').on('plotly_click', function(data) {{
                if (data.points && data.points.length > 0 && data.points[0].customdata !== undefined) {{
                    selectNode(data.points[0].customdata);
                }}
            }});
        }}
        
        function getHoverText(node) {{
            let status = [];
            if (node.is_fixed) status.push('FIXED');
            if (node.is_io) status.push('IO');
            return `<b>${{node.name}}</b><br>Type: ${{node.type}}<br>Status: ${{status.join(', ') || 'Movable'}}<br>Pos: (${{node.x.toFixed(1)}}, ${{node.y.toFixed(1)}})<br>Conn: ${{node.connections.length}}`;
        }}
        
        function selectNode(nodeIndex) {{
            selectedNodeIndex = nodeIndex;
            const node = nodesData[nodeIndex];
            
            document.getElementById('node-info').classList.add('active');
            document.getElementById('selected-name').textContent = node.name;
            document.getElementById('selected-index').textContent = node.id;
            document.getElementById('selected-type').textContent = node.type;
            document.getElementById('selected-position').textContent = `(${{node.x.toFixed(2)}}, ${{node.y.toFixed(2)}})`;
            
            let status = [];
            if (node.is_fixed) status.push('FIXED');
            if (node.is_io) status.push('IO');
            document.getElementById('selected-status').textContent = status.length > 0 ? status.join(', ') : 'Movable';
            document.getElementById('selected-connections').textContent = node.connections.length;
            
            if (hasInitPositions && document.getElementById('selected-displacement')) {{
                document.getElementById('selected-displacement').textContent = node.displacement ? node.displacement.toFixed(2) : '-';
            }}
            
            const connectedDiv = document.getElementById('connected-nodes');
            connectedDiv.innerHTML = '';
            node.connections.slice(0, 50).forEach(connIdx => {{
                const span = document.createElement('span');
                span.className = 'connected-node';
                span.textContent = nodesData[connIdx].name;
                span.onclick = () => selectNode(connIdx);
                connectedDiv.appendChild(span);
            }});
            if (node.connections.length > 50) {{
                const more = document.createElement('span');
                more.className = 'connected-node';
                more.textContent = `+${{node.connections.length - 50}} more`;
                connectedDiv.appendChild(more);
            }}
            
            highlightNode(nodeIndex, node.connections);
            document.getElementById('status').textContent = `Selected: ${{node.name}} (${{node.connections.length}} connections)`;
        }}
        
        function highlightNode(nodeIndex, connectedIndices) {{
            const node = nodesData[nodeIndex];
            const plotDiv = document.getElementById('plot');
            
            while (plotDiv.data.length > baseTraceCount) {{
                Plotly.deleteTraces('plot', -1);
            }}
            
            // Connected edges
            const connEdgeX = [], connEdgeY = [];
            connectedIndices.forEach(connIdx => {{
                connEdgeX.push(node.x, nodesData[connIdx].x, null);
                connEdgeY.push(node.y, nodesData[connIdx].y, null);
            }});
            
            if (connEdgeX.length > 0) {{
                Plotly.addTraces('plot', {{
                    x: connEdgeX, y: connEdgeY,
                    mode: 'lines',
                    line: {{ width: 2, color: colors.connectedEdge }},
                    hoverinfo: 'none'
                }});
            }}
            
            // Connected nodes
            const connNodes = connectedIndices.map(i => nodesData[i]);
            if (connNodes.length > 0) {{
                Plotly.addTraces('plot', {{
                    x: connNodes.map(n => n.x),
                    y: connNodes.map(n => n.y),
                    mode: 'markers',
                    marker: {{ size: 10, color: colors.connected, symbol: 'circle', line: {{ width: 1, color: 'white' }} }},
                    customdata: connNodes.map(n => n.id),
                    hoverinfo: 'text',
                    hovertext: connNodes.map(n => getHoverText(n))
                }});
            }}
            
            // Selected node
            Plotly.addTraces('plot', {{
                x: [node.x], y: [node.y],
                mode: 'markers',
                marker: {{ size: 16, color: colors.selected, symbol: 'star', line: {{ width: 2, color: 'white' }} }},
                customdata: [node.id],
                hoverinfo: 'text',
                hovertext: [getHoverText(node)]
            }});
        }}
        
        function clearSelection() {{
            selectedNodeIndex = null;
            document.getElementById('node-info').classList.remove('active');
            document.getElementById('status').textContent = 'Click on a node to see its connections';
            
            const plotDiv = document.getElementById('plot');
            while (plotDiv.data.length > baseTraceCount) {{
                Plotly.deleteTraces('plot', -1);
            }}
        }}
        
        function searchNode() {{
            const query = document.getElementById('search-input').value.trim().toLowerCase();
            if (!query) return;
            
            const found = nodesData.find(n => n.name.toLowerCase().includes(query) || n.id.toString() === query);
            
            if (found) {{
                selectNode(found.id);
                Plotly.relayout('plot', {{
                    'xaxis.range': [found.x - 30, found.x + 30],
                    'yaxis.range': [found.y - 30, found.y + 30]
                }});
            }} else {{
                document.getElementById('status').textContent = 'Node not found';
            }}
        }}
        
        function setupEventListeners() {{
            document.getElementById('show-edges').addEventListener('change', function() {{
                const idx = ioSitesData.length > 0 ? 1 : 0;
                Plotly.restyle('plot', {{ visible: this.checked }}, [idx]);
            }});
            
            if (ioSitesData.length > 0) {{
                document.getElementById('show-io-sites').addEventListener('change', function() {{
                    Plotly.restyle('plot', {{ visible: this.checked }}, [0]);
                }});
            }}
            
            if (hasInitPositions) {{
                document.getElementById('show-displacement')?.addEventListener('change', function() {{
                    if (this.checked) showDisplacementArrows();
                    else hideDisplacementArrows();
                }});
            }}
            
            document.getElementById('search-input').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') searchNode();
            }});
        }}
        
        function showDisplacementArrows() {{
            const annotations = [];
            const step = Math.max(1, Math.floor(nodesData.length / 100));
            
            for (let i = 0; i < nodesData.length; i += step) {{
                const node = nodesData[i];
                if (node.init_x !== undefined) {{
                    annotations.push({{
                        x: node.x, y: node.y,
                        ax: node.init_x, ay: node.init_y,
                        xref: 'x', yref: 'y',
                        axref: 'x', ayref: 'y',
                        showarrow: true,
                        arrowhead: 2,
                        arrowsize: 1,
                        arrowwidth: 1.5,
                        arrowcolor: 'rgba(231, 76, 60, 0.5)'
                    }});
                }}
            }}
            
            Plotly.relayout('plot', {{ annotations: annotations }});
        }}
        
        function hideDisplacementArrows() {{
            Plotly.relayout('plot', {{ annotations: [] }});
        }}
        
        init();
    </script>
</body>
</html>'''


# ============================================================================
# Main Visualization Functions - 修复版本
# ============================================================================

def visualize_gift_pipeline(cluster_layouts: Dict, 
                            output_dir: str = "viz_output",
                            show_all_arrows: bool = False,
                            arrow_sample_ratio: float = 0.5,
                            parser = None,
                            scl_file: str = None):
    """
    可视化GIFT Pipeline结果 - 修复版本
    
    Args:
        cluster_layouts: Pipeline生成的cluster布局
        output_dir: 输出目录
        show_all_arrows: 是否显示所有箭头
        arrow_sample_ratio: 箭头采样比例
        parser: FPGABookshelfParser实例（用于获取节点信息）
        scl_file: .scl文件路径（用于获取IO站点位置）
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 解析IO站点位置
    io_site_positions = None
    if scl_file and os.path.exists(scl_file):
        scl_parser = SCLParser()
        scl_parser.parse(scl_file)
        io_site_positions = scl_parser.get_io_positions()
        print(f"  Loaded {len(scl_parser.io_locations)} IO sites from .scl file")
    
    for cluster_id, layout in cluster_layouts.items():
        positions = layout['positions']
        init_positions = layout.get('init_location')
        node_indices = layout['node_indices']
        
        # 获取节点信息
        node_names = []
        node_types = {}
        fixed_nodes = set()
        io_nodes = set()
        adj_matrix = None
        
        if parser is not None:
            # 从parser获取完整信息
            for local_idx, global_idx in enumerate(node_indices):
                name = parser.idx_to_node_name.get(global_idx, f"node_{global_idx}")
                node_names.append(name)
                
                if name in parser.nodes:
                    node_info = parser.nodes[name]
                    node_types[local_idx] = node_info
                    
                    if node_info.get('is_io', False):
                        io_nodes.add(local_idx)
                
                if name in parser.placements:
                    if parser.placements[name].get('fixed', False):
                        fixed_nodes.add(local_idx)
            
            # 获取邻接矩阵
            full_adj = parser.build_adjacency_matrix()
            adj_matrix = full_adj[node_indices, :][:, node_indices]
        else:
            node_names = [f"node_{i}" for i in range(len(positions))]
        
        output_path = os.path.join(output_dir, f"gift_cluster_{cluster_id}.html")
        
        generate_interactive_html(
            positions=positions,
            adj_matrix=adj_matrix,
            node_names=node_names,
            node_types=node_types,
            fixed_nodes=fixed_nodes,
            io_nodes=io_nodes,
            init_positions=init_positions,
            io_site_positions=io_site_positions,
            title=f"GIFT Layout - Cluster {cluster_id}",
            output_path=output_path
        )
    
    print(f"  Generated {len(cluster_layouts)} interactive visualizations")


# ============================================================================
# SpecPart Core Implementation - 真正的Cut-Overlay聚类实现
# ============================================================================

class SpecPartTreeGenerator:
    """树生成器 - 用于SpecPart Cut-Overlay聚类"""
    
    def __init__(self, adj_matrix, x_features, y_features):
        self.adj_matrix = csr_matrix(adj_matrix)
        self.x_features = np.array(x_features)
        self.y_features = np.array(y_features)
        self.n = adj_matrix.shape[0]
    
    def _modify_weights_by_feature(self, feature):
        """根据特征向量距离修改边权重"""
        rows, cols = self.adj_matrix.nonzero()
        if len(rows) == 0:
            return self.adj_matrix
        
        new_weights = np.zeros(len(rows))
        for idx, (i, j) in enumerate(zip(rows, cols)):
            diff = abs(feature[i] - feature[j])
            new_weights[idx] = diff + 1e-10
        
        return csr_matrix((new_weights, (rows, cols)), shape=self.adj_matrix.shape)
    
    def gen_mst(self, feature):
        """生成基于特征的MST"""
        modified = self._modify_weights_by_feature(feature)
        mst = minimum_spanning_tree(modified)
        return csr_matrix(mst) + csr_matrix(mst).T
    
    def gen_path_tree(self, feature):
        """生成路径树 - 按特征值排序连接相邻节点"""
        order = np.argsort(feature)
        rows = order[:-1]
        cols = order[1:]
        weights = np.abs(feature[cols] - feature[rows]) + 1e-10
        tree = csr_matrix((weights, (rows, cols)), shape=(self.n, self.n))
        return tree + tree.T
    
    def generate_trees(self, num_trees=5):
        """生成多样化的树"""
        trees = []
        
        # MST based on x
        try:
            trees.append(self.gen_mst(self.x_features))
        except:
            pass
        
        # MST based on y
        try:
            trees.append(self.gen_mst(self.y_features))
        except:
            pass
        
        # Path tree based on x
        try:
            trees.append(self.gen_path_tree(self.x_features))
        except:
            pass
        
        # Path tree based on y
        try:
            trees.append(self.gen_path_tree(self.y_features))
        except:
            pass
        
        # MST based on x+y (diagonal)
        try:
            trees.append(self.gen_mst(self.x_features + self.y_features))
        except:
            pass
        
        # MST based on x-y (anti-diagonal)
        try:
            trees.append(self.gen_mst(self.x_features - self.y_features))
        except:
            pass
        
        return trees[:num_trees] if len(trees) > num_trees else trees


class SpecPartTreePartitioner:
    """树分区器 - 用于SpecPart Cut-Overlay聚类"""
    
    def __init__(self, tree, vertex_weights=None, ub_factor=10):
        self.tree = csr_matrix(tree)
        self.n = tree.shape[0]
        self.vertex_weights = vertex_weights if vertex_weights is not None else np.ones(self.n)
        self.ub_factor = ub_factor
        
        total = np.sum(self.vertex_weights)
        self.max_capacity = total * (50 + ub_factor) / 100
        self.min_capacity = total * (50 - ub_factor) / 100
    
    def partition_by_feature(self, feature, add_noise=False, noise_seed=42):
        """基于特征分区"""
        if add_noise:
            # 使用固定种子确保可复现性
            rng = np.random.RandomState(noise_seed)
            noise_scale = (feature.max() - feature.min() + 1e-6) * 0.01
            noise = rng.randn(len(feature)) * noise_scale
            feature = feature + noise
        
        order = np.argsort(feature)
        return self._sweep_partition(order)
    
    def _sweep_partition(self, order):
        """扫描分区 - 寻找最佳切割点"""
        n = len(order)
        cumsum = np.cumsum(self.vertex_weights[order])
        total = cumsum[-1]
        
        best_cut = float('inf')
        best_split = n // 2
        
        # 扫描中间60%的范围寻找最佳切割
        start = max(1, n // 5)
        end = min(n - 1, n * 4 // 5)
        
        for i in range(start, end):
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
        """计算切割代价"""
        part0 = set(order[:split_idx + 1])
        part1 = set(order[split_idx + 1:])
        
        cut = 0
        rows, cols = self.tree.nonzero()
        for i, j in zip(rows, cols):
            if i < j:
                if (i in part0 and j in part1) or (i in part1 and j in part0):
                    cut += self.tree[i, j]
        return cut


class SpecPartCutOverlayClustering:
    """Cut-Overlay聚类 - SpecPart核心算法"""
    
    def __init__(self, n, hyperedges):
        self.n = n
        self.hyperedges = hyperedges
    
    def generate_partitions(self, adj_matrix, x_features, y_features, 
                            ub_factor=10, num_trees=5):
        """生成多样化的分区"""
        partitions = []
        cuts = []
        
        # 生成树
        tree_gen = SpecPartTreeGenerator(adj_matrix, x_features, y_features)
        trees = tree_gen.generate_trees(num_trees)
        
        if len(trees) == 0:
            return self._simple_partitions(x_features, y_features)
        
        # 对每棵树进行分区
        for tree_idx, tree in enumerate(trees):
            partitioner = SpecPartTreePartitioner(tree, ub_factor=ub_factor)
            
            # 基于x分区
            try:
                p, c = partitioner.partition_by_feature(x_features)
                partitions.append(p)
                cuts.append(c)
            except:
                pass
            
            # 基于y分区
            try:
                p, c = partitioner.partition_by_feature(y_features)
                partitions.append(p)
                cuts.append(c)
            except:
                pass
            
            # 带噪声的分区（增加多样性，使用固定种子确保可复现）
            try:
                p, c = partitioner.partition_by_feature(x_features, add_noise=True, noise_seed=42 + tree_idx * 2)
                partitions.append(p)
                cuts.append(c)
            except:
                pass
            
            try:
                p, c = partitioner.partition_by_feature(y_features, add_noise=True, noise_seed=42 + tree_idx * 2 + 1)
                partitions.append(p)
                cuts.append(c)
            except:
                pass
        
        if len(partitions) == 0:
            return self._simple_partitions(x_features, y_features)
        
        return np.array(partitions), np.array(cuts)
    
    def _simple_partitions(self, x_features, y_features):
        """简单的基于坐标的分区（fallback）"""
        partitions = []
        
        median_x = np.median(x_features)
        partitions.append((x_features > median_x).astype(int))
        
        median_y = np.median(y_features)
        partitions.append((y_features > median_y).astype(int))
        
        combined = x_features + y_features
        partitions.append((combined > np.median(combined)).astype(int))
        
        diff = x_features - y_features
        partitions.append((diff > np.median(diff)).astype(int))
        
        # 四象限分区
        p = np.zeros(self.n, dtype=int)
        p[(x_features > median_x) & (y_features > median_y)] = 1
        p[(x_features <= median_x) & (y_features <= median_y)] = 1
        partitions.append(p)
        
        return np.array(partitions), np.zeros(len(partitions))
    
    def overlay_partitions(self, partition_matrix):
        """叠加分区形成聚类 - Cut-Overlay核心"""
        num_parts, n = partition_matrix.shape
        
        pattern_to_cluster = {}
        cluster_assignments = np.zeros(n, dtype=int)
        
        for v in range(n):
            pattern = tuple(partition_matrix[:, v])
            if pattern not in pattern_to_cluster:
                pattern_to_cluster[pattern] = len(pattern_to_cluster)
            cluster_assignments[v] = pattern_to_cluster[pattern]
        
        num_clusters = len(pattern_to_cluster)
        clusters = [[] for _ in range(num_clusters)]
        for v in range(n):
            clusters[cluster_assignments[v]].append(v)
        
        # 过滤空clusters
        clusters = [c for c in clusters if len(c) > 0]
        
        # 重新构建cluster_map
        cluster_map = {}
        for new_idx, cluster in enumerate(clusters):
            for v in cluster:
                cluster_map[v] = new_idx
        
        return clusters, cluster_map
    
    def select_best_partitions(self, partition_matrix, cuts, top_k=5):
        """选择最佳（多样性）分区"""
        if partition_matrix.shape[0] <= top_k:
            return partition_matrix
        
        # 去重
        unique_partitions = []
        unique_cuts = []
        seen = set()
        
        for i, p in enumerate(partition_matrix):
            pattern = tuple(p)
            if pattern not in seen:
                seen.add(pattern)
                unique_partitions.append(p)
                unique_cuts.append(cuts[i])
        
        if len(unique_partitions) <= top_k:
            return np.array(unique_partitions)
        
        sorted_idx = np.argsort(unique_cuts)[:top_k]
        return np.array([unique_partitions[i] for i in sorted_idx])


def _generate_specpart_clustering_html(
    positions: np.ndarray,
    clusters: List[List[int]],
    cluster_map: Dict[int, int],
    node_indices: List[int],
    cluster_id_prefix: str,
    output_dir: str
):
    """生成SpecPart聚类可视化HTML"""
    
    num_clusters = len(clusters)
    
    # 生成颜色
    colors = []
    for i in range(num_clusters):
        hue = i / max(num_clusters, 1)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 0.9)
        colors.append(f'rgb({int(r*255)},{int(g*255)},{int(b*255)})')
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>SpecPart Clustering - {cluster_id_prefix}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #ecf0f1;
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            background: rgba(0, 0, 0, 0.4);
            padding: 16px 24px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            font-size: 22px;
            background: linear-gradient(90deg, #4A90D9, #9B59B6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-top: 10px;
        }}
        .stat-item {{
            background: rgba(255, 255, 255, 0.1);
            padding: 10px 20px;
            border-radius: 8px;
        }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #4A90D9; }}
        .stat-label {{ font-size: 12px; color: #888; }}
        #plot {{
            width: 100%;
            height: calc(100vh - 200px);
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}
        .cluster-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.05);
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Cut-Overlay Clustering: {cluster_id_prefix}</h1>
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value">{len(node_indices)}</div>
                <div class="stat-label">Total Nodes</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{num_clusters}</div>
                <div class="stat-label">Sub-clusters</div>
            </div>
        </div>
        <div class="cluster-legend">
'''
    
    for i, cluster in enumerate(clusters):
        html += f'''            <div class="legend-item">
                <div class="legend-color" style="background: {colors[i % len(colors)]};"></div>
                Cluster {i}: {len(cluster)} nodes
            </div>
'''
    
    html += '''        </div>
    </div>
    <div id="plot"></div>
    <script>
        var data = [
'''
    
    for i, cluster in enumerate(clusters):
        x_vals = [float(positions[idx, 0]) for idx in cluster]
        y_vals = [float(positions[idx, 1]) for idx in cluster]
        labels = [f"Node {node_indices[idx]} (local: {idx})" for idx in cluster]
        
        html += f'''            {{
                x: {x_vals},
                y: {y_vals},
                mode: 'markers',
                type: 'scatter',
                name: 'Cluster {i} ({len(cluster)})',
                text: {json.dumps(labels)},
                marker: {{
                    size: 8,
                    color: '{colors[i % len(colors)]}'
                }},
                hoverinfo: 'text'
            }},
'''
    
    html += '''        ];
        
        var layout = {
            paper_bgcolor: '#1a1a2e',
            plot_bgcolor: '#1a1a2e',
            font: { color: '#ecf0f1' },
            xaxis: { 
                title: 'X', 
                gridcolor: '#2d2d44', 
                zerolinecolor: '#2d2d44' 
            },
            yaxis: { 
                title: 'Y', 
                gridcolor: '#2d2d44', 
                zerolinecolor: '#2d2d44',
                scaleanchor: 'x',
                scaleratio: 1
            },
            hovermode: 'closest',
            showlegend: true,
            legend: {
                bgcolor: 'rgba(0,0,0,0.3)',
                bordercolor: 'rgba(255,255,255,0.1)',
                borderwidth: 1
            },
            margin: { l: 50, r: 50, t: 20, b: 50 }
        };
        
        Plotly.newPlot('plot', data, layout, {responsive: true, scrollZoom: true});
    </script>
</body>
</html>'''
    
    html_file = os.path.join(output_dir, f"{cluster_id_prefix}_clustering.html")
    with open(html_file, 'w') as f:
        f.write(html)
    
    print(f"  [SpecPart] Saved visualization: {html_file}")


def run_specpart_clustering_with_visualization(
    adj_matrix,
    hyperedges: List[Tuple],
    positions: np.ndarray,
    node_indices: List[int],
    cluster_id_prefix: str = "cluster",
    ub_factor: int = 10,
    num_trees: int = 5,
    best_solns: int = 5,
    output_dir: str = "viz_output",
    verbose: bool = True,
    random_seed: int = 42,
    # === NEW: recursion controls (safe defaults; call sites don't need to pass) ===
    min_cluster_size: int = 50,
    max_depth: int = 10,
    use_hmetis=True,  # 确保此参数传递
    hmetis_path="./hmetis"  # 传递hmetis的路径
) -> Tuple[List[List[int]], Dict[int, int], Dict]:
    """
    运行 SpecPart(完整Step4~7) + 递归二分聚类，并生成可视化

    返回值仍保持原接口：
      clusters: List[List[local_idx]]
      cluster_map: Dict[local_idx -> cluster_id]
      stats: dict
    """
    os.makedirs(output_dir, exist_ok=True)
    np.random.seed(random_seed)

    n = len(node_indices)
    if n == 0:
        return [], {}, {"num_nodes": 0, "num_clusters": 0, "cluster_sizes": []}

    if verbose:
        x_features = positions[:, 0]
        y_features = positions[:, 1]
        print(f"  [SpecPart] Running (RECURSIVE full SpecPart) on {n} nodes, {len(hyperedges)} hyperedges")
        print(f"  [SpecPart] Position range: X=[{x_features.min():.1f}, {x_features.max():.1f}], "
              f"Y=[{y_features.min():.1f}, {y_features.max():.1f}]")
        print(f"  [SpecPart] Recursion: min_cluster_size={min_cluster_size}, max_depth={max_depth}, use_hmetis={use_hmetis}")

    # ----------------------------
    # Use recursive engine
    # ----------------------------

    pipeline = GIFTSpecPartPipeline()

    # recursive_bisection_clustering expects:
    # - adj_matrix / hyperedges / positions are LOCAL to this cluster
    # - node_indices are GLOBAL ids (used only for mapping & output)
    clusters_global = pipeline.recursive_bisection_clustering(
        adj_matrix=adj_matrix,
        hyperedges=hyperedges,
        node_indices=node_indices,
        positions=positions,                 # 关键：复用你 Phase2 的 GIFT 坐标，不重新跑 GIFT
        reuse_parent_positions=True,         # 下层子问题也复用坐标（子集切片）
        ub_factor=ub_factor,
        num_trees=num_trees,
        best_solns=best_solns,
        use_hmetis=use_hmetis,
        hmetis_path=hmetis_path,
        min_cluster_size=min_cluster_size,
        max_depth=max_depth,
        verbose=verbose,
        random_seed=random_seed
    )

    # ----------------------------
    # Convert GLOBAL clusters -> LOCAL clusters
    # ----------------------------
    g2l = {g: i for i, g in enumerate(node_indices)}
    clusters: List[List[int]] = []
    for cl in clusters_global:
        # 防御性：跳过不在映射里的节点（一般不会发生）
        loc = [g2l[g] for g in cl if g in g2l]
        if loc:
            clusters.append(loc)

    # 构建 cluster_map: local_idx -> cluster_id
    cluster_map: Dict[int, int] = {}
    for cid, cl in enumerate(clusters):
        for v in cl:
            cluster_map[v] = cid

    # 如果有遗漏点，兜底：单独成簇
    if len(cluster_map) < n:
        missing = [i for i in range(n) if i not in cluster_map]
        for v in missing:
            cid = len(clusters)
            clusters.append([v])
            cluster_map[v] = cid

    if verbose:
        print(f"  [SpecPart] Final clusters after recursion: {len(clusters)}")
        print(f"  [SpecPart] Cluster sizes: {[len(c) for c in clusters]}")

    # ----------------------------
    # Visualization (keep your original HTML generator)
    # ----------------------------
    if verbose:
        print(f"  [SpecPart] Generating visualization...")

    try:
        _generate_specpart_clustering_html(
            positions, clusters, cluster_map,
            node_indices, cluster_id_prefix, output_dir
        )
    except Exception as e:
        print(f"  [SpecPart] Warning: Visualization failed: {e}")

    stats = {
        "num_nodes": n,
        "num_hyperedges": len(hyperedges),
        "num_clusters": len(clusters),
        "cluster_sizes": [len(c) for c in clusters],
        "recursive_min_cluster_size": min_cluster_size,
        "recursive_max_depth": max_depth,
        "use_hmetis": use_hmetis,
    }
    return clusters, cluster_map, stats



def export_clustering_results(
    clusters: List[List[int]],
    cluster_map: Dict[int, int],
    node_indices: List[int],
    output_dir: str,
    cluster_id_prefix: str = "cluster"
):
    """导出聚类结果"""
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, f"{cluster_id_prefix}_assignments.txt"), 'w') as f:
        for node_idx, cluster_id in sorted(cluster_map.items()):
            f.write(f"{node_idx}\t{cluster_id}\n")
    
    with open(os.path.join(output_dir, f"{cluster_id_prefix}_clusters.json"), 'w') as f:
        json.dump({'clusters': clusters}, f, indent=2)


# ============================================================================
# Pipeline Integration Class
# ============================================================================

class InteractiveVisualizationApp:
    """交互式可视化应用 - 与Pipeline整合"""
    
    def __init__(self, output_dir: str = "viz_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.cluster_layouts = {}
        self.parser = None
        self.scl_parser = SCLParser()
        self.io_site_positions = None
        
    def load_from_pipeline(self,
                           cluster_layouts: Dict,
                           parser,
                           scl_file: Optional[str] = None):
        """从Pipeline结果加载数据"""
        self.cluster_layouts = cluster_layouts
        self.parser = parser
        
        if scl_file and os.path.exists(scl_file):
            self.scl_parser.parse(scl_file)
            self.io_site_positions = self.scl_parser.get_io_positions()
            print(f"  Loaded {len(self.scl_parser.io_locations)} IO site locations from .scl")
    
    def visualize_cluster(self, cluster_id: int) -> str:
        """可视化单个cluster"""
        if cluster_id not in self.cluster_layouts:
            raise ValueError(f"Cluster {cluster_id} not found")
        
        layout = self.cluster_layouts[cluster_id]
        node_indices = layout['node_indices']
        positions = layout['positions']
        init_positions = layout.get('init_location')
        
        node_names, node_types, fixed_nodes, io_nodes = [], {}, set(), set()
        
        for local_idx, global_idx in enumerate(node_indices):
            name = self.parser.idx_to_node_name.get(global_idx, f"node_{global_idx}")
            node_names.append(name)
            
            if name in self.parser.nodes:
                node_info = self.parser.nodes[name]
                node_types[local_idx] = node_info
                if node_info.get('is_io', False):
                    io_nodes.add(local_idx)
            
            if name in self.parser.placements:
                if self.parser.placements[name].get('fixed', False):
                    fixed_nodes.add(local_idx)
        
        adj_matrix = self.parser.build_adjacency_matrix()
        sub_adj = adj_matrix[node_indices, :][:, node_indices]
        
        output_path = os.path.join(self.output_dir, f"cluster_{cluster_id}_interactive.html")
        
        generate_interactive_html(
            positions=positions,
            adj_matrix=sub_adj,
            node_names=node_names,
            node_types=node_types,
            fixed_nodes=fixed_nodes,
            io_nodes=io_nodes,
            init_positions=init_positions,
            io_site_positions=self.io_site_positions,
            title=f"Cluster {cluster_id} - FPGA Layout",
            output_path=output_path
        )
        
        return output_path
    
    def visualize_all_clusters(self) -> List[str]:
        """可视化所有clusters"""
        output_files = []
        
        for cluster_id in self.cluster_layouts:
            try:
                output_path = self.visualize_cluster(cluster_id)
                output_files.append(output_path)
            except Exception as e:
                print(f"  Warning: Failed to visualize cluster {cluster_id}: {e}")
        
        index_path = self._create_index_page(output_files)
        output_files.append(index_path)
        
        return output_files
    
    def _create_index_page(self, cluster_files: List[str]) -> str:
        """创建索引页"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>FPGA Cluster Visualizations</title>
    <style>
        body { font-family: system-ui; background: #1a1a2e; color: #ecf0f1; padding: 40px; }
        h1 { color: #4A90D9; }
        .cluster-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; margin-top: 30px; }
        .cluster-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 20px; transition: transform 0.2s; }
        .cluster-card:hover { transform: translateY(-5px); background: rgba(255,255,255,0.1); }
        .cluster-card a { color: #4A90D9; text-decoration: none; font-size: 18px; font-weight: 600; }
        .cluster-info { color: #888; font-size: 14px; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>FPGA Cluster Visualizations</h1>
    <p>Click on a cluster to view its interactive visualization.</p>
    <div class="cluster-list">
'''
        for f in cluster_files:
            filename = os.path.basename(f)
            cluster_id = filename.replace('cluster_', '').replace('_interactive.html', '')
            
            if cluster_id.isdigit() and int(cluster_id) in self.cluster_layouts:
                n_nodes = len(self.cluster_layouts[int(cluster_id)]['node_indices'])
            else:
                n_nodes = '?'
            
            html += f'''
        <div class="cluster-card">
            <a href="{filename}">Cluster {cluster_id}</a>
            <div class="cluster-info">{n_nodes} nodes</div>
        </div>
'''
        
        html += '''
    </div>
</body>
</html>'''
        
        index_path = os.path.join(self.output_dir, "index.html")
        with open(index_path, 'w') as f:
            f.write(html)
        
        return index_path


if __name__ == "__main__":
    print("visualization_clustering.py - Fixed version")
    print("This module should be imported and used with the main pipeline.")