# FPGA Clustering Pipeline Migration / Final Placer Interface

本文档面向“把现有 clustering + cluster placement + net reweighting 流程迁移到另一台服务器，并用新的 final placer 替代当前 final placement”的场景。

主入口：

```bash
python run_complete_flow_with_json.py --params_json <params.json>
```

当前推荐边界是：保留 Phase 1-4，生成完整 `<output_dir>/4_final_input/`；新的 placer 只消费 `4_final_input`，不要改前面的 clustering 流程。

## Package Scope

本迁移包目标：在新服务器上能从输入 benchmark 和参数 JSON 跑到完整 `4_final_input`。

迁移包包含：

```text
run_complete_flow_with_json.py
main_pipeline_with_viz.py
fpga_clustering_pipeline_gift.py
gift_specpart_complete.py
cluster_placement_integration.py
net_reweighting_integration.py
cluster_conductance_analysis.py
visualization_clustering.py
adaptive_params.py
adaptive_profiles.json
PROJECT_STRUCTURE.md
MIGRATION_NEW_PLACER.md
requirements_migration.txt
run_complete_flow_params_template.json
configs/ispd2016_FPGA01_phase4.json ... configs/ispd2016_FPGA12_phase4.json
data/ispd2016/FPGA01 ... data/ispd2016/FPGA12
tools/DREAMPlaceFPGA/
hmetis_api/
external/HypergraphPartitioning-main/SpecPart/
external/HypergraphPartitioning-main/K_SpecPart/
```

迁移包不包含：历史实验输出、日志、Titan benchmark/config、batch tuner、span/fanout optional helper。

## Runtime Stages

`run_complete_flow_with_json.py` 的主要阶段：

```text
Phase 1: Louvain + GIFT + SpecPart clustering
Phase 2: DREAMPlaceFPGA cluster-level placement
Phase 3: net reweighting
Phase 4: build final placer input under <output_dir>/4_final_input
Phase 5: optional current DREAMPlaceFPGA final placement
```

替换 final placer 时只运行到 Phase 4。参数中必须保持：

```json
"misc": {
  "run_final_placement": false
}
```

如果 `run_final_placement=true` 或 CLI 传入 `--run_final_placement`，脚本会继续调用当前 DREAMPlaceFPGA final placer，这不是新 placer 接入时需要的路径。

## Input Interface

### 1. Benchmark Input

`benchmark_dir` 指向一个 Bookshelf/ISPD2016 FPGA benchmark 目录。目录至少需要包含：

```text
design.aux
design.nodes
design.nets
design.pl
design.scl
design.lib
```

可选文件：

```text
design.wts       # Bookshelf weight file；没有有效内容也可以是空/占位文件
design.weights   # net weight file；输入阶段可不存在，Phase 3/4 会生成新的 weights
design.dcp       # 原始 benchmark 附带文件；流程通常不直接依赖，但 ISPD2016 数据中保留
```

`design.aux` 应能引用同目录下的 `.nodes/.nets/.pl/.scl/.lib/.wts`。参数 JSON 中 `aux=null` 时，脚本会使用 benchmark 目录里的默认 `.aux`；如果文件名不是 `design.aux`，显式设置：

```json
"aux": "xxx.aux"
```

包内已带 ISPD2016：

```text
data/ispd2016/FPGA01
data/ispd2016/FPGA02
...
data/ispd2016/FPGA12
```

### 2. Parameter JSON Input

推荐使用 sectioned JSON，例如：

```json
{
  "benchmark_dir": "data/ispd2016/FPGA01",
  "output_dir": "outputs/ispd2016_FPGA01_phase4",
  "aux": null,
  "dreamplace_path": "tools/DREAMPlaceFPGA",
  "clustering": {
    "min_cluster_size": 337,
    "resolution": 1.062341388894038,
    "gift_scale": 0.599632013883368,
    "ub_factor": 12,
    "num_trees": 5,
    "best_solns": 12,
    "max_cluster_size": 2250,
    "specpart_mode": "gift_then_spectral",
    "specpart_timeout": 21600,
    "specpart_per_job_timeout": 240,
    "specpart_num_workers": 3,
    "max_fanout": 150
  },
  "cluster_placement": {
    "run_cluster_placement": true,
    "cluster_iteration": 1000,
    "place_density_lb_addon": 2.0868876089074524,
    "sigma_ratio": 0.6494737788369305,
    "gpu": 0,
    "cluster_base_weight": 2.963738421488964,
    "cluster_fixed_cluster_weight": 19.748178679498128,
    "cluster_random_seed": 1674,
    "max_fanout": 150
  },
  "net_reweighting": {
    "intra_sub": 1.4423860832213171,
    "intra": 1.1532243716426578,
    "inter": 0.7248875225454047,
    "density_skip_threshold": 1.3
  },
  "final_placement": {
    "final_iteration": 2000,
    "learning_rate": 0.013080584886744205,
    "net_weight_anneal_iters": 250,
    "density_weight": 79999999.99999993,
    "node_area_adjust_overflow": 0.15,
    "random_seed": 7116,
    "routability_opt_flag": 1,
    "gamma": 6.809759346743754
  },
  "misc": {
    "visualize": false,
    "run_final_placement": false,
    "skip_clustering": false
  }
}
```

关键字段说明：

| Field | Required | Meaning |
| --- | --- | --- |
| `benchmark_dir` | yes | 输入 benchmark 目录。相对路径会先按当前工作目录解析；若不存在，则按代码包根目录解析。 |
| `output_dir` | yes | 输出目录；相对路径同样会按当前工作目录/代码包根目录解析，`4_final_input` 会写到这里下面。 |
| `aux` | no | `.aux` 文件名；`null` 表示自动使用 benchmark 目录默认 aux。 |
| `dreamplace_path` | yes for Phase 2 | bundled DREAMPlaceFPGA 路径；即使不跑 final placement，cluster-level placement 仍需要它。 |
| `clustering.*` | yes | Louvain/GIFT/SpecPart 参数。 |
| `cluster_placement.*` | yes if cluster placement enabled | Phase 2 cluster-level placement 参数。 |
| `net_reweighting.*` | yes | Phase 3 权重参数。`density_skip_threshold=1.3` 时，若 conductance/density 规则触发，会强制 weights=1。 |
| `final_placement.*` | optional for new placer | 主要用于生成 `dreamplace_config.json` metadata；新 placer 可忽略。 |
| `misc.run_final_placement` | yes | 替换 final placer 时必须为 `false`。 |


路径可迁移性说明：包内配置使用相对路径（如 `data/ispd2016/FPGA01`、`tools/DREAMPlaceFPGA`）。运行时脚本会把这些路径解析成当前服务器上的实际绝对路径，不会把打包机器上的 `/export/home/...` 或 `/work/...` 写死到配置中。

CLI 参数优先级高于 JSON。比如下面命令会覆盖 JSON 里的 `output_dir`：

```bash
python run_complete_flow_with_json.py \
  --params_json configs/ispd2016_FPGA01_phase4.json \
  --output_dir outputs/test_fpga01
```

## Environment And Dependencies

完整新服务器环境清单见：`ENVIRONMENT_SETUP.md`。这里列出迁移包运行到 `4_final_input` 的硬要求。

Gurobi 是本项目必需依赖，不再按 optional 处理。迁移包不能包含 Gurobi Optimizer 本体或 license；新服务器必须提供有效 Gurobi 安装和 license，并且 Python `gurobipy` 与 Julia `Gurobi.jl` 都要能实际 solve 一个小模型。

推荐优先复现已验证环境：

```text
Linux x86_64; tested on Ubuntu 18.04.5 / glibc 2.27
As-shipped DREAMPlaceFPGA ops require GLIBC_2.27; glibc 2.17 needs container or rebuild
Python 3.8.5; bundled DREAMPlaceFPGA ops are cpython-38 shared objects
PyTorch 1.7.1; DREAMPlaceFPGA upstream targets PyTorch 1.6/1.7/1.8
gurobipy 11.0.3; target server must have valid Gurobi license
Julia 1.9.4 + Gurobi.jl 1.9.2
CMake >= 3.8.2, GCC/G++/make available for rebuilds
32-bit runtime libraries for bundled hMETIS
```

最小安装步骤：

```bash
# From package root after creating/activating a Python 3.8 environment
pip install -r requirements_migration.txt

# If target Gurobi is not 11.0.x, replace gurobipy==11.0.3 in requirements_migration.txt
# with the matching target-server version before pip install.

julia -e 'using Pkg; Pkg.add([
  "ArgParse", "CSV", "Clustering", "Combinatorics", "DataFrames",
  "DataStructures", "Graphs", "LightGraphs", "IterativeSolvers", "JSON",
  "JuMP", "GLPK", "Cbc", "Gurobi", "LDLFactorizations", "Laplacians",
  "LinearMaps", "Match", "MathOptInterface", "Metis", "MultivariateStats",
  "ParallelKMeans", "Shuffle", "SimpleGraphs", "SimpleTraits",
  "SimpleWeightedGraphs"
])'
julia -e 'using Pkg; Pkg.develop(path="external/HypergraphPartitioning-main/K_SpecPart/GraphLaplacians")'
```

Ubuntu/Debian 上还需要系统工具和 hMETIS 32-bit runtime：

```bash
sudo apt-get update
sudo apt-get install -y build-essential gcc g++ make cmake git tar gzip unzip file \
  python3-dev pkg-config capnproto libcapnp-dev libcairo2 libcairo2-dev libffi-dev
sudo dpkg --add-architecture i386
sudo apt-get update
sudo apt-get install -y libc6:i386 libstdc++6:i386
sudo apt-get install -y libgcc1:i386 || sudo apt-get install -y libgcc-s1:i386
```

从包根目录设置运行环境，`GUROBI_HOME` 和 license 路径按新服务器实际值替换：

```bash
export JULIA_CMD=$(which julia)
export SPECPART_ROOT=$PWD/external/HypergraphPartitioning-main
export HMETIS_EXEC=$PWD/hmetis_api/hmetis_api/src/hmetis
export SPECPART_BACKEND=julia
export MPLBACKEND=Agg

export GUROBI_HOME=/opt/gurobi1103/linux64
export PATH=$GUROBI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:$LD_LIBRARY_PATH
export GRB_LICENSE_FILE=/path/to/gurobi.lic
# or: export GRB_LICENSE_FILE=27000@license-server-host
```

修正 `GUROBI_HOME` 后重建 Julia Gurobi.jl：

```bash
julia -e 'using Pkg; ENV["GUROBI_HOME"] = get(ENV, "GUROBI_HOME", ""); Pkg.build("Gurobi")'
```

依赖和 Gurobi license 验证：

```bash
python - <<'PY'
import numpy, scipy, matplotlib, sklearn, tqdm, networkx
import torch, pyunpack, patoolib, cairocffi, pkgconfig, capnp, igraph
import gurobipy as gp
print('Python deps OK')
m = gp.Model('license_smoke')
m.Params.OutputFlag = 0
x = m.addVar(lb=0.0, ub=1.0, name='x')
m.setObjective(x, gp.GRB.MAXIMIZE)
m.optimize()
assert m.Status == gp.GRB.OPTIMAL, m.Status
print('Python Gurobi solve OK')
PY

PYTHONPATH=$PWD/tools/DREAMPlaceFPGA:$PYTHONPATH python - <<'PY'
from dreamplacefpga.ops.hpwl import hpwl_cpp
print('DREAMPlaceFPGA ops OK')
PY

julia -e 'using ArgParse, JSON, Graphs, LightGraphs, JuMP, GLPK, Cbc, Gurobi; using GraphLaplacians; println("Julia deps import OK")'
julia <<'JL'
using JuMP, Gurobi, MathOptInterface
const MOI = MathOptInterface
model = JuMP.Model(Gurobi.Optimizer)
JuMP.set_silent(model)
JuMP.@variable(model, 0 <= x <= 1)
JuMP.@objective(model, Max, x)
JuMP.optimize!(model)
@assert JuMP.termination_status(model) == MOI.OPTIMAL JuMP.termination_status(model)
println("Julia Gurobi solve OK")
JL
test -x hmetis_api/hmetis_api/src/hmetis
```

如果 Python 不是 3.8、PyTorch ABI 不匹配、或 DREAMPlaceFPGA compiled op import 失败，需要在目标服务器重编：

```bash
cd tools/DREAMPlaceFPGA
rm -rf build
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$(pwd)/.. -DPYTHON_EXECUTABLE=$(which python)
make -j$(nproc)
make install
```

`CPLEX` 仍然是可选项，只在启用 CPLEX-specific 路径时需要。

关于 glibc 2.17：它不是算法本身的硬要求，但当前打包的 DREAMPlaceFPGA 预编译 `.so` 已引用 `GLIBC_2.27` 符号，所以在 glibc 2.17 系统上不能保证原样 import。若目标服务器是 CentOS/RHEL 7，建议用 Ubuntu 18.04+ 容器运行，或在该服务器上重编 `tools/DREAMPlaceFPGA`。另外包内 32-bit hMETIS 需要 `GLIBCXX_3.4.21`，也要在目标服务器验证。

## Run To Generate 4_final_input

从包根目录运行：

```bash
cd fpga_clustering_pipeline_gift_full_migration_20260513
export JULIA_CMD=julia
export SPECPART_ROOT=$PWD/external/HypergraphPartitioning-main
export HMETIS_EXEC=$PWD/hmetis_api/hmetis_api/src/hmetis
python run_complete_flow_with_json.py --params_json configs/ispd2016_FPGA01_phase4.json
```

成功后输出：

```text
outputs/ispd2016_FPGA01_phase4/1_clustering/
outputs/ispd2016_FPGA01_phase4/2_cluster_placement/
outputs/ispd2016_FPGA01_phase4/3_net_reweighting/
outputs/ispd2016_FPGA01_phase4/4_final_input/
```

如果只想确认接口文件生成，不要传 `--run_final_placement`。

## 4_final_input Contract For New Placer

新的 placer 应把 `<output_dir>/4_final_input` 当作工作输入目录。核心文件：

| File | Meaning |
| --- | --- |
| `design.aux` | Bookshelf file list, points to generated `design.nodes/design.nets/design.wts/design.pl/design.scl/design.lib`. |
| `design.nodes` | 原始 nodes/cell type 信息。 |
| `design.nets` | 原始或按 `max_fanout` 处理后的 netlist。 |
| `design.scl` | FPGA site/grid/architecture 信息。 |
| `design.lib` | cell library。 |
| `design.pl` | fixed node placement；通常只包含 fixed/IO/macros 等固定对象。 |
| `movable_init.pl` | movable cell 初始位置，由 cluster placement + intra-cluster scatter 生成；格式为 `<node> <x> <y> <z>`。 |
| `design.weights` | Phase 3 生成的 net weights；格式为 `<net_name> <weight>`。如果 density skip 触发，所有 weight 为 1。 |
| `design.wts` | Bookshelf compatibility placeholder。 |
| `dreamplace_config.json` | 当前 DREAMPlaceFPGA final placement config；对新 placer 主要作为 metadata。 |

新 placer 最小输入通常是：

```text
design.aux
design.nodes
design.nets
design.pl
design.scl
design.lib
movable_init.pl
design.weights
```

推荐新 placer adapter 命令形态：

```bash
NEW_PLACER \
  --aux <output_dir>/4_final_input/design.aux \
  --init <output_dir>/4_final_input/movable_init.pl \
  --weights <output_dir>/4_final_input/design.weights \
  --out <output_dir>/4_final_input/results_new_placer
```

如果新 placer 需要单个 merged `.pl`，应将 `design.pl` 的 fixed nodes 与 `movable_init.pl` 的 movable nodes 合并，并保留 fixed marker。

## Code Replacement Point

如果希望仍由 `run_complete_flow_with_json.py` 启动新 placer，只替换 Phase 5：

```text
run_complete_flow_with_json.py: after Phase 4, inside the run_final_placement block
```

不要改 Phase 4，因为 Phase 4 是稳定接口，负责写出 `4_final_input`。

adapter 需要满足：

```text
cwd = <output_dir>/4_final_input
stdout/stderr 写到 final_placement.log 或新 placer 自己的日志
失败时返回非 0 exit code
结果写到 results_new_placer/ 或兼容现有分析脚本的 results/design/design.gp.pl
```
