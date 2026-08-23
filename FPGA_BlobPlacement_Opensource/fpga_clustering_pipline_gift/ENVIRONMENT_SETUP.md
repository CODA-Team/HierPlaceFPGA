# Environment Setup For The Migration Package

本文档用于新服务器部署迁移包，并保证流程能从 benchmark + 参数 JSON 跑到完整 `<output_dir>/4_final_input`。新的 final placer 可以只消费 `4_final_input`；这里不要求跑当前 DREAMPlaceFPGA final placement。

重要修正：本项目把 Gurobi 当作必需依赖处理。迁移包不能包含 Gurobi Optimizer 本体或 license；新服务器必须已经安装 Gurobi，并且 license 对运行用户可用。只安装 Python/Julia 包但没有有效 license，不能算环境配置完成。

## 1. Tested Baseline

已验证环境来自 Docker 容器 `638feef5705b`：

| Item | Tested value |
| --- | --- |
| OS | Ubuntu 18.04.5 LTS x86_64 |
| glibc | 2.27 |
| Python | 3.8.5 (`/opt/conda/bin/python`) |
| PyTorch | 1.7.1 |
| gurobipy | 11.0.3 import OK; current container license expired, so solve test cannot pass there |
| Julia Gurobi.jl | 1.9.2 import OK; current container has no valid root license |
| NumPy / SciPy | 1.22.4 / 1.7.3 |
| Matplotlib | 3.4.3 |
| scikit-learn | 1.3.2 |
| pycapnp import name | `capnp`, version 1.1.0 |
| igraph | 0.11.8 |
| Julia | 1.9.4 |
| CMake | 3.21.0 |
| GCC / G++ | 7.5.0 |
| GNU Make | 4.1 |

推荐优先复现这个组合，特别是 Python 3.8 + PyTorch 1.7.1 + gurobipy 11.0.3 + Julia 1.9.4/Gurobi.jl 1.9.2。`glibc 2.27` 是已验证 baseline，同时也是当前包内预编译 DREAMPlaceFPGA operators 的实际动态链接要求：扫描 `.so` 后发现最高符号版本为 `GLIBC_2.27`。因此迁移包“原样运行”不能只依赖 glibc 2.17。包内 DREAMPlaceFPGA 已编译算子文件名是 `*.cpython-38-x86_64-linux-gnu.so`，所以原样运行还需要 Python 3.8 ABI。

## 2. System Packages

Linux x86_64 是硬要求。Ubuntu/Debian 上建议安装：

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential gcc g++ make cmake git \
  tar gzip unzip bzip2 xz-utils file \
  python3-dev pkg-config \
  capnproto libcapnp-dev \
  libcairo2 libcairo2-dev libffi-dev
```

`hmetis_api/hmetis_api/src/hmetis` 是包内自带的 32-bit ELF 程序。新服务器如果没有 32-bit runtime，会出现 `No such file or directory`、`not found` 或 `ld-linux.so.2` 缺失。Ubuntu/Debian 需要启用 i386 runtime：

```bash
sudo dpkg --add-architecture i386
sudo apt-get update
sudo apt-get install -y libc6:i386 libstdc++6:i386
# Ubuntu 18.04 通常还需要 libgcc1:i386；Ubuntu 20.04+ 通常是 libgcc-s1:i386
sudo apt-get install -y libgcc1:i386 || sudo apt-get install -y libgcc-s1:i386
```

验证 hMETIS：

```bash
test -x hmetis_api/hmetis_api/src/hmetis
ldd hmetis_api/hmetis_api/src/hmetis
hmetis_api/hmetis_api/src/hmetis | head
```

CentOS 7 / RHEL 7 常见是 glibc 2.17。该版本可以作为“从源码重编后的目标运行环境”，但不保证能直接运行本包预编译产物。当前包内 native binary 检查结果：

```text
DREAMPlaceFPGA operators: require up to GLIBC_2.27, example symbol expf@GLIBC_2.27
hMETIS binary: glibc symbols are old enough, but libstdc++ requires up to GLIBCXX_3.4.21
```

如果目标服务器只有 glibc 2.17，推荐二选一：

```text
1. 使用 Docker/Apptainer/Singularity 跑 Ubuntu 18.04+ 用户态环境。
2. 在 glibc 2.17 机器上用目标 Python 3.8 + PyTorch 1.x 重新编译 tools/DREAMPlaceFPGA，并确认 32-bit hMETIS 的 libstdc++ runtime 提供 GLIBCXX_3.4.21。
```

## 3. Gurobi Environment Required

Gurobi 是必需项，原因有两个：

```text
external/HypergraphPartitioning-main/SpecPart/SpectralRefinement.jl 直接 using Gurobi
gift_specpart_complete.py 和 SpecPart/ilp_k_solver.py 有 Python gurobipy ILP 路径
```

新服务器必须同时满足：

```text
Gurobi Optimizer installed, e.g. /opt/gurobi1103/linux64
Valid Gurobi license visible to the exact runtime user
Python gurobipy installed and version-compatible
Julia Gurobi.jl installed/built against the same Gurobi installation
```

### 3.1 Point To Existing Gurobi Installation

如果新服务器已有 Gurobi，例如 `/opt/gurobi1103/linux64`，从包根目录或 shell startup 文件设置：

```bash
export GUROBI_HOME=/opt/gurobi1103/linux64
export PATH=$GUROBI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:$LD_LIBRARY_PATH
```

license 设置三选一，按新服务器实际情况使用：

```bash
# Named-user / academic license file
export GRB_LICENSE_FILE=/path/to/gurobi.lic

# Floating/token server license, example only
export GRB_LICENSE_FILE=27000@license-server-host

# Web License Service, if your license uses WLS
export GRB_WLSACCESSID=<access-id>
export GRB_WLSSECRET=<secret>
export GRB_LICENSEID=<license-id>
```

不要假设 root、docker 用户、普通用户共享同一个 license。必须用实际运行 pipeline 的用户执行下面验证。

### 3.2 Python gurobipy

`requirements_migration.txt` 默认写入已验证版本：

```text
gurobipy==11.0.3
```

如果新服务器 Gurobi Optimizer 不是 11.0.x，建议把 `requirements_migration.txt` 里的 `gurobipy==11.0.3` 改成目标服务器匹配版本，例如：

```bash
pip install 'gurobipy==<target-gurobi-version>'
```

Python Gurobi 验证必须做 solve，不只是 import：

```bash
python - <<'PY'
import gurobipy as gp
print('gurobipy version:', gp.gurobi.version())
m = gp.Model('license_smoke')
m.Params.OutputFlag = 0
x = m.addVar(lb=0.0, ub=1.0, name='x')
m.setObjective(x, gp.GRB.MAXIMIZE)
m.optimize()
assert m.Status == gp.GRB.OPTIMAL, m.Status
print('Python Gurobi solve OK, obj =', m.ObjVal)
PY
```

### 3.3 Julia Gurobi.jl

安装和重建 Julia Gurobi.jl：

```bash
julia -e 'using Pkg; Pkg.add("Gurobi")'
julia -e 'using Pkg; ENV["GUROBI_HOME"] = get(ENV, "GUROBI_HOME", ""); Pkg.build("Gurobi")'
```

如果 `GUROBI_HOME` 为空或指错路径，`Pkg.build("Gurobi")` 可能会链接错误库或找不到库。修正 `GUROBI_HOME` 后必须重新 build。

Julia Gurobi 验证也必须做 solve：

```bash
julia <<'JL'
using JuMP, Gurobi, MathOptInterface
const MOI = MathOptInterface
model = JuMP.Model(Gurobi.Optimizer)
JuMP.set_silent(model)
JuMP.@variable(model, 0 <= x <= 1)
JuMP.@objective(model, Max, x)
JuMP.optimize!(model)
@assert JuMP.termination_status(model) == MOI.OPTIMAL JuMP.termination_status(model)
println("Julia Gurobi solve OK, obj = ", JuMP.objective_value(model))
JL
```

如果报 `No Gurobi license found`、`License expired`、`HostID mismatch`、`User is not in license`，说明 Gurobi 环境没有完成；继续跑本项目会在需要 Gurobi 的路径失败。

## 4. Python Environment

### 4.1 Required Python Version

- 推荐：Python 3.8。
- 不推荐直接用 Python 3.10/3.11/3.12/3.13 跑迁移包原始 DREAMPlaceFPGA，因为包内 `.so` 是 CPython 3.8 ABI。
- 如果必须使用非 Python 3.8，必须重新编译 `tools/DREAMPlaceFPGA`，并重新跑 smoke test。

### 4.2 Create Environment

Conda 示例：

```bash
conda create -n fpga_gift python=3.8 -y
conda activate fpga_gift
python -m pip install --upgrade pip setuptools wheel
```

安装 Python 包：

```bash
pip install -r requirements_migration.txt
```

如果使用 CPU-only PyTorch wheel，可按目标服务器和 pip 源选择对应 wheel。DREAMPlaceFPGA upstream 支持 PyTorch 1.6/1.7/1.8；不要直接使用 PyTorch 2.x，除非你重新编译并验证 DREAMPlaceFPGA operators。

### 4.3 Required Python Packages

`requirements_migration.txt` 已合并 core pipeline、DREAMPlaceFPGA runtime 与 Gurobi 依赖：

| Package | Why needed |
| --- | --- |
| `numpy`, `scipy` | graph/netlist processing, DREAMPlaceFPGA runtime |
| `matplotlib` | plotting hooks and DREAMPlaceFPGA utility imports; headless can use `MPLBACKEND=Agg` |
| `scikit-learn` | clustering metrics / seed setup |
| `tqdm` | progress display |
| `networkx` | compatibility dependency retained for graph utilities |
| `torch` | DREAMPlaceFPGA runtime and compiled ops |
| `pyunpack`, `patool` | DREAMPlaceFPGA archive utilities (`patool` imports as `patoolib`) |
| `cairocffi`, `pkgconfig` | DREAMPlaceFPGA drawing/build utility imports |
| `pycapnp` | FPGA interchange schema support; imports as `capnp` |
| `igraph` | DREAMPlaceFPGA graph utility import |
| `setuptools`, `wheel` | Python package/build support |
| `gurobipy` | required for Python Gurobi ILP paths and license verification |

Python dependency verification：

```bash
python - <<'PY'
import numpy, scipy, matplotlib, sklearn, tqdm, networkx
import torch, pyunpack, patoolib, cairocffi, pkgconfig, capnp, igraph
import gurobipy as gp
print('Python deps OK')
print('torch', torch.__version__)
print('gurobipy', gp.gurobi.version())
PY
```

DREAMPlaceFPGA compiled-op verification：

```bash
PYTHONPATH=$PWD/tools/DREAMPlaceFPGA:$PYTHONPATH python - <<'PY'
import torch
from dreamplacefpga.ops.hpwl import hpwl_cpp
print('DREAMPlaceFPGA hpwl_cpp OK')
PY
```

## 5. Julia / SpecPart Environment

Julia is required for SpecPart/K_SpecPart paths used in Phase 1. 已验证版本是 Julia 1.9.4。

安装 Julia 包，包括必需的 `Gurobi`：

```bash
julia -e 'using Pkg; Pkg.add([
  "ArgParse", "CSV", "Clustering", "Combinatorics", "DataFrames",
  "DataStructures", "Graphs", "LightGraphs", "IterativeSolvers", "JSON",
  "JuMP", "GLPK", "Cbc", "Gurobi", "LDLFactorizations", "Laplacians",
  "LinearMaps", "Match", "MathOptInterface", "Metis", "MultivariateStats",
  "ParallelKMeans", "Shuffle", "SimpleGraphs", "SimpleTraits",
  "SimpleWeightedGraphs"
])'
```

注册包内本地 Julia package，并确保 Gurobi.jl 链接到目标服务器的 Gurobi：

```bash
julia -e 'using Pkg; Pkg.develop(path="external/HypergraphPartitioning-main/K_SpecPart/GraphLaplacians")'
julia -e 'using Pkg; ENV["GUROBI_HOME"] = get(ENV, "GUROBI_HOME", ""); Pkg.build("Gurobi")'
```

Julia dependency verification：

```bash
julia -e 'using ArgParse, CSV, Clustering, Combinatorics, DataFrames, DataStructures, Graphs, LightGraphs, IterativeSolvers, JSON, JuMP, GLPK, Cbc, Gurobi, LDLFactorizations, Laplacians, LinearMaps, Match, MathOptInterface, Metis, MultivariateStats, ParallelKMeans, Shuffle, SimpleGraphs, SimpleTraits, SimpleWeightedGraphs; using GraphLaplacians; println("Julia deps import OK")'
```

Gurobi solve verification 见第 3 节。只通过 import 不够，必须确认 Python 和 Julia 都能实际 optimize 一个小模型。

`CPLEX` 仍然是可选项，只有启用 CPLEX-specific 路径时才需要：

```bash
julia -e 'using Pkg; Pkg.add("CPLEX")'
```

## 6. DREAMPlaceFPGA

`tools/DREAMPlaceFPGA` 已随包一起迁移，用于 Phase 2 cluster-level placement。即使不跑 final placement，Phase 2 仍需要它。

### 6.1 Run As Shipped

原样运行要求：

```text
Python 3.8
PyTorch 1.6/1.7/1.8 compatible runtime, tested with 1.7.1
Linux x86_64; as-shipped operators require glibc symbols up to GLIBC_2.27
```

CPU-only 可以运行。CUDA/GPU 是可选项；如果新服务器有 CUDA 并希望 GPU 加速，需要 PyTorch/CUDA/driver 版本匹配。

### 6.2 Rebuild When ABI Mismatch

以下情况必须重编 DREAMPlaceFPGA：

```text
Python 版本不是 3.8
PyTorch major/minor ABI 不兼容
目标服务器 glibc/libstdc++ 低于预编译产物要求，或 compiled op import 失败
需要切换 CUDA/GPU build
```

重编命令：

```bash
cd tools/DREAMPlaceFPGA
rm -rf build
mkdir build
cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$(pwd)/.. -DPYTHON_EXECUTABLE=$(which python)
make -j$(nproc)
make install
```

重编后必须重新运行 compiled-op verification 和 FPGA01 smoke test。

## 7. Required Environment Variables

从包根目录设置：

```bash
export JULIA_CMD=$(which julia)
export SPECPART_ROOT=$PWD/external/HypergraphPartitioning-main
export HMETIS_EXEC=$PWD/hmetis_api/hmetis_api/src/hmetis
export SPECPART_BACKEND=julia
export MPLBACKEND=Agg

# Required if Gurobi is installed outside the Python/Julia package defaults.
export GUROBI_HOME=/opt/gurobi1103/linux64
export PATH=$GUROBI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:$LD_LIBRARY_PATH
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

`GRB_LICENSE_FILE` 可以是 license 文件路径，也可以是 floating license server，例如 `27000@license-server-host`。如果使用 WLS license，改用 `GRB_WLSACCESSID`、`GRB_WLSSECRET`、`GRB_LICENSEID`。

`PYTHONPATH` 通常由流程在调用 DREAMPlaceFPGA 时自动处理；手工调试 DREAMPlaceFPGA 时可加：

```bash
export PYTHONPATH=$PWD/tools/DREAMPlaceFPGA:$PYTHONPATH
```

性能相关变量可按服务器调整：

```bash
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
```

## 8. Package Smoke Test

在新服务器解压后，从包根目录运行。先做 Gurobi solve verification，再跑 pipeline：

```bash
cd fpga_clustering_pipeline_gift_full_migration_20260513
export JULIA_CMD=$(which julia)
export SPECPART_ROOT=$PWD/external/HypergraphPartitioning-main
export HMETIS_EXEC=$PWD/hmetis_api/hmetis_api/src/hmetis
export SPECPART_BACKEND=julia
export MPLBACKEND=Agg

python run_complete_flow_with_json.py \
  --params_json configs/ispd2016_FPGA01_phase4.json \
  --output_dir outputs/smoke_FPGA01_phase4
```

成功标准：

```text
Python Gurobi solve verification 通过
Julia Gurobi solve verification 通过
pipeline 命令返回 0
outputs/smoke_FPGA01_phase4/4_final_input/ 存在
4_final_input/design.aux 存在
4_final_input/design.nodes 存在
4_final_input/design.nets 存在
4_final_input/design.pl 存在
4_final_input/design.scl 存在
4_final_input/design.lib 存在
4_final_input/movable_init.pl 存在且非空
4_final_input/design.weights 存在且非空
```

不要为了 smoke test 传 `--run_final_placement`；新 placer 接入只需要 Phase 4 输出。

## 9. Disk / Runtime Notes

- 当前完整迁移包 tar 约 1.2 GB，解压后约数 GB；ISPD2016 全 benchmark 和 DREAMPlaceFPGA 占主要空间。
- 每次运行会在 `output_dir` 生成 Phase 1-4 中间结果；FPGA01 已验证约数分钟，FPGA12 会显著更久、更占内存和磁盘。
- 建议新服务器预留至少 20 GB 可用空间用于解压、smoke test 和若干输出目录；跑全部 FPGA01-FPGA12 应预留更多空间。
