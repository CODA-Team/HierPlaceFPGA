# FPGA Clustering Pipeline Parameter Tuner

这个tuner用于自动优化 `fpga_clustering_pipline_gift` 项目的参数。

## 目录结构

```
tuner/
├── tuner_configs.py       # 参数配置和基线PPA定义
├── tuner_worker.py        # Worker实现，执行单次优化运行
├── tuner_train.py         # 主训练脚本，协调优化过程
├── tuner_utils.py         # 工具函数
├── tuner_analyze.py       # 结果分析和可视化
├── configspace.json       # 超参数搜索空间定义
├── run_tuner.sh          # 启动脚本
└── README_TUNER.md       # 本文件
```

## 依赖安装

首先安装tuner所需的依赖：

```bash
cd /export/home/keli/ZPJ_FCCM/fpga_clustering_pipline_gift
pip install -r tuner/requirements.txt
```

主要依赖包括：
- `hpbandster`: BOHB优化器
- `ConfigSpace`: 超参数空间定义
- `Pyro4`: 分布式通信（HPBandSter需要）
- `pandas`, `matplotlib`: 结果分析和可视化

### 验证安装

运行测试脚本验证设置：

```bash
python tuner/test_tuner_setup.py
```

如果所有测试通过，即可开始使用tuner。

## 快速开始

### 1. 修改配置

编辑 `run_tuner.sh`，设置以下关键参数：

```bash
# 基准测试目录
BENCHMARK_DIR="/work/fpga_clustering_pipline_gift/data/ispd2016/FPGA03"

# DREAMPlace路径
DREAMPLACE_PATH="/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA"

# 优化配置
N_ITERATIONS=50        # BOHB迭代次数
N_WORKERS=4           # 并行worker数量
```

### 2. 更新基线PPA

编辑 `tuner_configs.py`，更新 `CLUSTERING_BASE_PPA` 字典，添加你的基准测试基线结果：

```python
CLUSTERING_BASE_PPA = {
    "FPGA03": {
        "hpwl": 3e6,      # 更新为实际基线HPWL
        "runtime": 1000,   # 更新为实际基线运行时间（秒）
        "overflow": 0.15,  # 更新为实际基线overflow
    },
}
```

基线PPA用于归一化优化目标。建议先用默认参数运行一次完整流程获取基线。

### 3. 运行tuner

```bash
cd /export/home/keli/ZPJ_FCCM/fpga_clustering_pipline_gift
./tuner/run_tuner.sh
```

## 优化的参数

tuner会优化以下参数（在 `configspace.json` 中定义）：

### Clustering参数
- `min_cluster_size`: Louvain最小cluster大小 (30-100)
- `resolution`: Louvain分辨率 (0.5-2.0)
- `gift_scale`: GIFT初始位置范围 (0.3-0.8)

### Cluster Placement参数
- `utilization`: Cluster-level虚拟节点大小利用率 (0.8-1.5)
- `sigma_ratio`: Sub-cluster内部散布的sigma比率 (0.7-1.0)
- `cluster_base_weight`: Cluster-level网络基础权重 (0.1-5.0)
- `cluster_fixed_cluster_weight`: 固定节点与cluster节点之间网络的增强权重 (5.0-100.0)

### Net Reweighting参数
- `intra_sub`: 同一sub-cluster内网络权重 (1.0-2.0)
- `intra`: 同一cluster内跨sub-cluster网络权重 (0.8-1.5)
- `inter`: 跨cluster网络权重 (0.5-1.2)

### Final Placement参数
- `learning_rate`: 学习率 (0.001-0.05, log scale)

## 优化模式

### 单目标优化（默认）

优化一个加权目标函数：
```
cost = hpwl_ratio * hpwl_norm + overflow_ratio * overflow_norm + runtime_ratio * runtime_norm
```

在 `run_tuner.sh` 中设置权重：
```bash
MULTIOBJ=false
HPWL_RATIO=1.0
RUNTIME_RATIO=0.3
OVERFLOW_RATIO=0.5
```

### 多目标优化

同时优化HPWL、overflow和runtime，生成Pareto前沿：

```bash
MULTIOBJ=true
NUM_PARETO=5  # 提议的Pareto点数量
```

## 结果分析

### 输出目录结构

```
logs_tuner_YYYYMMDD_HHMMSS/
├── configs.json           # 所有采样的配置
├── results.json           # 所有运行结果
├── run-X-Y-Z/            # 每次运行的详细输出
│   ├── params.json       # 使用的参数
│   ├── flow.log          # 流程日志
│   └── 1_clustering/     # 完整的流程输出
│       2_cluster_placement/
│       3_net_reweighting/
│       4_final_input/
└── best_cfgs/            # 最佳配置
    ├── FPGA03_best_config.json   # 最佳参数（单目标）
    ├── FPGA03.pareto.png         # Pareto曲线（多目标）
    └── run-X-Y-Z/                # 最佳运行的完整输出
```

### 查看最佳配置

单目标优化：
```bash
cat logs_tuner_*/best_cfgs/FPGA03_best_config.json
```

多目标优化：
```bash
# 查看Pareto曲线
display logs_tuner_*/best_cfgs/FPGA03.pareto.png

# 查看Pareto点
python -c "
import pickle
df = pickle.load(open('logs_tuner_*/best_cfgs/FPGA03.dataframe.pkl', 'rb'))
print(df.head())
"
```

## 高级用法

### 自定义搜索空间

编辑 `configspace.json` 修改参数范围：

```json
{
  "hyperparameters": [
    {
      "name": "min_cluster_size",
      "type": "uniform_int",
      "lower": 30,
      "upper": 100,
      "default": 50
    }
  ]
}
```

### 重用最佳参数

在后续优化中从之前的最佳配置开始：

```bash
# 在 run_tuner.sh 中设置
REUSE_PARAMS="./logs_tuner_prev/best_cfgs/FPGA03_best_config.json"
```

### 并行GPU使用

```bash
# 使用所有GPU
GPU_POOL="-1"

# 使用特定GPU
GPU_POOL="0,1,2,3"
```

### Python API使用

也可以直接使用Python API：

```python
import os
os.chdir('/export/home/keli/ZPJ_FCCM/fpga_clustering_pipline_gift')

# 启动master
os.system("""
python tuner/tuner_train.py \\
    --n_iterations 50 \\
    --n_workers 4 \\
    --log_dir ./logs_test \\
    --run_id test_run \\
    --run_args benchmark_dir=/path/to/benchmark dreamplace_path=/path/to/DREAMPlace
""")
```

## 故障排查

### 问题：Worker超时

增加超时时间，在 `tuner_worker.py` 中修改：
```python
result = subprocess.run(
    cmd,
    timeout=7200  # 增加到更大的值
)
```

### 问题：GPU内存不足

减少并行worker数量：
```bash
N_WORKERS=2  # 减少worker数量
```

### 问题：找不到基线PPA

在 `tuner_configs.py` 中添加你的benchmark：
```python
CLUSTERING_BASE_PPA = {
    "YOUR_BENCHMARK": {
        "hpwl": 1e6,
        "runtime": 600,
        "overflow": 0.15,
    },
}
```

然后在 `run_tuner.sh` 中设置：
```bash
BASE_PPA="YOUR_BENCHMARK"
```

## 参考

- HPBandSter文档: https://github.com/automl/HpBandSter
- BOHB论文: https://arxiv.org/abs/1807.01774
- 原始DREAMPlaceFPGA tuner: /export/home/keli/ZPJ_FCCM/DREAMPlaceFPGA_to/tuner/

## 联系

如有问题，请查看日志文件或联系开发者。

