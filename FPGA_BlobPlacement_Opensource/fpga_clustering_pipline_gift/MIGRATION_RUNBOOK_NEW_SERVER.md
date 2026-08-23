# 新服务器迁移与快速验证手册

本文档对应本迁移包内的最新代码，目标是：在新服务器任意路径解压后，能够跑完整个 clustering -> cluster placement -> `4_final_input` 生成流程，并能判断当前 DREAMPlaceFPGA native ops 是否需要 rebuild。

## 1. 迁移包内容

包内主目录是：

```bash
fpga_clustering_pipline_gift/
```

关键内容：

- `run_complete_flow_with_json.py`：主入口。
- `convert_public_release_benchmark.py`：将 `public_release/case_N + Arch` 转为本框架可读 Bookshelf 输入。
- `cluster_placement_integration.py`：cluster-level DREAMPlaceFPGA 输入生成/运行，已加入 public_release 类型兼容。
- `cluster_conductance_analysis.py`：density gate；当 `cluster_weighted_mean_density + subcluster_weighted_mean_density > 1.3` 时强制 net weights 全为 `1.0`。
- `Arch/`：新 benchmark 的 architecture 文件。
- `public_release/`：新 benchmark 的 bookshelf-like netlist case_1 到 case_11。
- `data/ispd2016/`：ISPD2016 Bookshelf benchmark。
- `tools/DREAMPlaceFPGA/`：当前流程使用的 DREAMPlaceFPGA 源码、build 目录和已安装 native ops；已排除 5.7GB 原始压缩包和实验输出。
- `external/HypergraphPartitioning-main/`：SpecPart / K_SpecPart 最小运行源码；包内路径已改为相对路径/环境变量，不依赖旧服务器绝对路径。
- `hmetis_api/`：K_SpecPart 使用的 hMETIS 可执行文件。
- `scripts/`：环境检查、smoke run、DREAMPlaceFPGA rebuild 脚本。

不包含旧实验输出目录；新服务器运行会重新生成输出。

## 2. 解压后第一步

```bash
tar -xzf fpga_clustering_pipeline_migration_20260515_154555.tar.gz
cd fpga_clustering_pipeline_migration_20260515_154555/fpga_clustering_pipline_gift
```

推荐先设置包内相对路径环境变量：

```bash
export FPGA_ROOT=$PWD
export PYTHONPATH=$FPGA_ROOT/tools/DREAMPlaceFPGA:${PYTHONPATH:-}
export SPECPART_ROOT=$FPGA_ROOT/external/HypergraphPartitioning-main
export K_SPECPART_JL=$SPECPART_ROOT/K_SpecPart/K_SpecPartWrapper.jl
export HMETIS_EXEC=$FPGA_ROOT/hmetis_api/hmetis_api/src/hmetis
```

这些变量都使用 `$PWD`，所以包移动到任何服务器、任何目录都可以用。

## 3. 推荐 Python/Conda 环境

当前包内预编译 DREAMPlaceFPGA native ops 是 Python 3.8 扩展，文件名类似：

```bash
tools/DREAMPlaceFPGA/dreamplacefpga/ops/*/*.cpython-38-x86_64-linux-gnu.so
```

因此优先使用 Python 3.8。推荐：

```bash
conda env create -f environment_new_server.yml
conda activate fpga_cluster_place
```

如果你不用 `environment_new_server.yml`，手动环境至少需要：

```bash
conda create -n fpga_cluster_place python=3.8 -y
conda activate fpga_cluster_place
conda install -c pytorch pytorch=1.7.1 torchvision=0.8.2 cudatoolkit=11.0 -y
pip install -r requirements_new_server.txt
```

说明：

- PyTorch 1.7.1 不是“C 库”，而是 Python package + C++/CUDA native backend；DREAMPlaceFPGA 的 `.so` 是按 Python/PyTorch ABI 编译的。
- 即使新服务器暂时不用 GPU，也建议安装 `cudatoolkit=11.0`，因为当前 PyTorch/DREAMPlaceFPGA 栈是按 CUDA 11.0 时代的 ABI 构建的。
- 如果新服务器必须用不同 PyTorch 或 Python 版本，通常需要 rebuild DREAMPlaceFPGA。

## 4. Julia / SpecPart 环境

安装 Julia 后，在包根目录运行：

```bash
julia --startup-file=no julia/install_julia_deps.jl
```

该脚本会安装/开发这些关键包：

- `JSON`, `ArgParse`
- `Graphs`, `LightGraphs`, `SimpleWeightedGraphs`, `SimpleGraphs`, `SimpleTraits`
- `DataStructures`, `Combinatorics`, `Shuffle`
- `Laplacians`, `LinearMaps`, `IterativeSolvers`, `LDLFactorizations`, `MultivariateStats`, `Metis`
- `JuMP`, `Gurobi`
- 本包内 `external/HypergraphPartitioning-main/K_SpecPart/GraphLaplacians`

验证：

```bash
julia --startup-file=no -e 'using JSON, DataStructures, LightGraphs, SimpleWeightedGraphs, Shuffle; println("Julia base packages OK")'
julia --startup-file=no -e 'include(ENV["K_SPECPART_JL"]); println("K_SpecPartWrapper OK")'
```

## 5. Gurobi 必须单独确认

本项目 Python 端和 Julia 端都可能用到 Gurobi；新服务器只按 Python 包安装还不够，license 和 native library 也必须可用。

设置示例，具体版本按新服务器实际安装路径改：

```bash
export GUROBI_HOME=/opt/gurobi1103/linux64
export PATH=$GUROBI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}
export GRB_LICENSE_FILE=$HOME/gurobi.lic
```

Python 检查：

```bash
python - <<'PY'
import gurobipy as gp
m = gp.Model()
m.setParam("OutputFlag", 0)
x = m.addVar(lb=0.0)
m.setObjective(x)
m.optimize()
print("gurobipy OK", gp.gurobi.version())
PY
```

Julia 检查：

```bash
julia --startup-file=no -e 'using Pkg; Pkg.build("Gurobi")'
julia --startup-file=no -e 'using Gurobi; println("Gurobi.jl OK")'
```

如果这里失败，先修 Gurobi，不要继续跑大 case；否则 SpecPart/ILP fallback 相关路径会不稳定。

## 6. hMETIS 32-bit 依赖

包内 hMETIS 是 32-bit ELF：

```bash
file hmetis_api/hmetis_api/src/hmetis
```

如果运行时报 `No such file or directory` 但文件明明存在，通常是新服务器缺 32-bit runtime，而不是路径问题。

常见修复：

- Ubuntu/Debian：`sudo apt-get install libc6-i386 lib32stdc++6`
- CentOS/RHEL：`sudo yum install glibc.i686 libstdc++.i686`

快速验证：

```bash
cat > /tmp/tiny.hgr <<'EOF'
1 2
1 2
EOF
$HMETIS_EXEC /tmp/tiny.hgr 2 5 1 1 1 0 1 0 0
ls /tmp/tiny.hgr.part.2
```

## 7. 是否需要 rebuild DREAMPlaceFPGA

先运行：

```bash
scripts/check_environment_new_server.sh
```

如果该脚本第 `[4/7]` 步的 DREAMPlaceFPGA native imports 全部通过，通常不需要 rebuild。

必须 rebuild 的情况：

- Python 不是 3.8；当前 `.so` 是 `cpython-38`。
- PyTorch 不是 1.7.x，或者 `torch._C._GLIBCXX_USE_CXX11_ABI` 与当前 build 不一致。
- `import dreamplacefpga.ops...` 报 `undefined symbol`、`GLIBCXX_x.y.z not found`、`libtorch*.so not found`、`libcudart*.so not found`。
- 新服务器 glibc/libstdc++ 比当前 build 需求更老，预编译 `.so` 不能加载。
- 你决定换 CUDA/PyTorch/GCC toolchain。

当前 build 使用旧 PyTorch ABI，rebuild 默认参数：

```bash
scripts/rebuild_dreamplacefpga.sh
```

等价手动命令：

```bash
cd tools/DREAMPlaceFPGA
rm -rf build
mkdir build && cd build
cmake .. \
  -DCMAKE_INSTALL_PREFIX=$(pwd)/.. \
  -DPYTHON_EXECUTABLE=$(which python) \
  -DCMAKE_CXX_ABI=0
make -j$(nproc)
make install
```

如果你安装的 PyTorch 显示：

```bash
python - <<'PY'
import torch
print(torch._C._GLIBCXX_USE_CXX11_ABI)
PY
```

输出是 `True`，则 rebuild 时需要尝试：

```bash
CMAKE_CXX_ABI=1 scripts/rebuild_dreamplacefpga.sh
```

关于 glibc：不要求固定 glibc 2.27。关键是“预编译 `.so` 所需的 GLIBC/GLIBCXX symbol，新服务器必须提供”。如果新服务器是 glibc 2.17，能否直接用取决于 `.so` 实际引用的 symbol；最可靠的判断就是第 `[4/7]` 步 native import 是否通过。不通过就应在新服务器本机 rebuild，或者使用与当前容器一致的 Docker 环境。

## 8. 快速验证流程

### 8.1 只检查环境和格式转换

```bash
scripts/check_environment_new_server.sh
```

通过标准：最后输出：

```bash
Environment smoke check PASSED
```

这个检查会做：Python 编译、Python import、DREAMPlaceFPGA native op import、hMETIS 小图、Julia/K_SpecPart load、`public_release case_1` 转换。

### 8.2 跑一个极短完整 smoke case

```bash
scripts/run_smoke_case1_iter20.sh
```

输出目录默认：

```bash
smoke_public_release_case1_iter20/
```

关键检查点：

```bash
ls smoke_public_release_case1_iter20/4_final_input
ls smoke_public_release_case1_iter20/4_final_input/design.nodes
ls smoke_public_release_case1_iter20/4_final_input/design.nets
ls smoke_public_release_case1_iter20/4_final_input/design.pl
ls smoke_public_release_case1_iter20/4_final_input/design.scl
ls smoke_public_release_case1_iter20/4_final_input/design.lib
```

`iter20` 只验证链路能跑通，不代表 placement 质量，也不要求 overflow 收敛。

## 9. 正式运行接口

### 9.1 public_release / Arch 新 benchmark 输入

输入接口：

- `--benchmark_dir public_release`：包含 `case_1.nodes/.nets/.timing` 等文件的目录。
- `--convert_arch_dir Arch`：包含 `fpga.scl`, `fpga.lib`, `fpga.clk`。
- `--convert_case case_1`：选择具体 case。
- `--convert_public_release`：开启格式转换。

只生成新 placer 需要的 `4_final_input`，不跑当前 final DREAMPlaceFPGA：

```bash
python run_complete_flow_with_json.py \
  --convert_public_release \
  --benchmark_dir public_release \
  --convert_arch_dir Arch \
  --convert_case case_1 \
  --output_dir run_case1_for_new_placer \
  --dreamplace_path tools/DREAMPlaceFPGA \
  --min_cluster_size 100 \
  --max_cluster_size 1000 \
  --num_trees 1 \
  --best_solns 1 \
  --specpart_num_seeds 1 \
  --specpart_num_workers 2 \
  --specpart_timeout 1800 \
  --specpart_per_job_timeout 60 \
  --specpart_mode gift_single \
  --cluster_iteration 1000 \
  --final_iteration 2000 \
  --max_fanout 500 \
  --gpu 0 \
  --no_viz
```

输出给新 placer 的目录：

```bash
run_case1_for_new_placer/4_final_input
```

如果还要用当前 DREAMPlaceFPGA 做 final placement 对照，才加：

```bash
--run_final_placement --final_dreamplace_compat
```

这会额外生成：

```bash
run_case1_for_new_placer/4_final_input_dreamplace_compat
```

注意：`4_final_input` 是真实 new benchmark 类型；`4_final_input_dreamplace_compat` 只是为了当前 DREAMPlaceFPGA 能读而生成的兼容视图。接新 placer 时应优先使用真实的 `4_final_input`。

### 9.2 ISPD2016 benchmark 输入

输入接口：

- `--benchmark_dir data/ispd2016/FPGA01`
- `--aux design.aux`
- 不需要 `--convert_public_release`

示例：

```bash
python run_complete_flow_with_json.py \
  --benchmark_dir data/ispd2016/FPGA01 \
  --aux design.aux \
  --output_dir run_ispd_FPGA01_for_new_placer \
  --dreamplace_path tools/DREAMPlaceFPGA \
  --min_cluster_size 100 \
  --max_cluster_size 1000 \
  --num_trees 1 \
  --best_solns 1 \
  --specpart_num_seeds 1 \
  --specpart_num_workers 2 \
  --specpart_mode gift_single \
  --cluster_iteration 1000 \
  --final_iteration 2000 \
  --max_fanout 500 \
  --gpu 0 \
  --no_viz
```

输出给新 placer 的目录：

```bash
run_ispd_FPGA01_for_new_placer/4_final_input
```

## 10. 参数 JSON 接口

主程序支持：

```bash
--params_json path/to/params.json
```

JSON 可以是 flat key-value，也可以按 section 写：

```json
{
  "benchmark_conversion": {
    "convert_public_release": true,
    "benchmark_dir": "public_release",
    "convert_arch_dir": "Arch",
    "convert_case": "case_1"
  },
  "clustering": {
    "min_cluster_size": 100,
    "max_cluster_size": 1000,
    "specpart_mode": "gift_single",
    "num_trees": 1,
    "best_solns": 1,
    "specpart_num_seeds": 1,
    "specpart_num_workers": 2
  },
  "cluster_placement": {
    "cluster_iteration": 1000,
    "max_fanout": 500
  },
  "final_placement": {
    "final_iteration": 2000,
    "run_final_placement": false,
    "final_dreamplace_compat": false
  },
  "dreamplace": {
    "dreamplace_path": "tools/DREAMPlaceFPGA",
    "gpu": 0
  },
  "misc": {
    "output_dir": "run_case1_for_new_placer",
    "visualize": false
  }
}
```

CLI 参数优先级高于 JSON。

## 11. 输出接口给新 placer

新 placer 应读取：

```bash
<output_dir>/4_final_input/
```

核心文件：

- `design.aux`：Bookshelf file list。
- `design.nodes`：节点名和 cell type。
- `design.nets`：net/pin 连接。
- `design.pl`：由 cluster/subcluster flow 生成的初始位置；`FIXED` 节点保留 fixed 标记。
- `design.scl`：site/resource map。
- `design.lib`：cell/pin library。
- `design.weights` / `design.wts`：net weights。density gate 触发时这里会全为 `1.0`。
- `design.clk`, `design.timing`, `design.clock_nets`, `design.metadata.json`：public_release 转换带来的 sidecar 信息。

不要把 `4_final_input_dreamplace_compat` 当成新 placer 的真实输入；它会把部分类型 alias 成当前 DREAMPlaceFPGA 能识别的类型。

## 12. 常见失败与处理

- `ModuleNotFoundError: torch`：Python 环境没有激活，或 PyTorch 没装。
- `No module named sknetwork`：安装 `scikit-network`。
- DREAMPlaceFPGA `undefined symbol`：PyTorch/Python ABI 不匹配，执行 `scripts/rebuild_dreamplacefpga.sh`。
- `libtorch_cpu.so not found`：Conda 环境的 PyTorch library 不在运行时搜索路径中；确认 `conda activate` 后再跑。
- hMETIS “No such file or directory”：通常缺 32-bit runtime，按第 6 节安装。
- `GurobiError: License ...`：license 没配置；先修 `GRB_LICENSE_FILE` 或 license server。
- Julia `Package ... not found`：运行 `julia/install_julia_deps.jl`。
- cluster placement overflow 未达到 target：这不一定阻塞 `4_final_input` 生成；但正式实验应提高 `cluster_iteration`，并检查 log 中 final overflow。

## 13. 最短迁移检查顺序

新服务器上按这个顺序做，能最快定位问题：

```bash
cd fpga_clustering_pipeline_migration_20260515_154555/fpga_clustering_pipline_gift
conda activate fpga_cluster_place
export FPGA_ROOT=$PWD
export PYTHONPATH=$FPGA_ROOT/tools/DREAMPlaceFPGA:${PYTHONPATH:-}
export SPECPART_ROOT=$FPGA_ROOT/external/HypergraphPartitioning-main
export K_SPECPART_JL=$SPECPART_ROOT/K_SpecPart/K_SpecPartWrapper.jl
export HMETIS_EXEC=$FPGA_ROOT/hmetis_api/hmetis_api/src/hmetis
scripts/check_environment_new_server.sh
scripts/run_smoke_case1_iter20.sh
```

如果 `check_environment_new_server.sh` 失败在 DREAMPlaceFPGA native import，先 rebuild。不要直接跑大 case。
