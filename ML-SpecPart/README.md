# ML-SpecPart

ML-SpecPart is the ML-guided hypergraph-partitioning component of
HierPlaceFPGA.  It combines HyperCutNet GNN inference, TritonPart guided
partitioning, and the Julia SpecPart Cut-Overlay implementation.

## Repository layout

```text
ML-SpecPart/
├── HyperCutNet/     # Python/DGL model, training and inference
├── TritonPart/      # OpenROAD-based guided hypergraph partitioner
├── SpecPart/        # Julia Cut-Overlay implementation
├── checkpoints/     # released model checkpoints
└── tools/           # conversion, inference, and orchestration scripts
```

The repository contains source code and model checkpoints.  OpenROAD is built
locally; generated builds, experiment outputs, and graph datasets are not
tracked.  The three-model flow requires graph data in HyperCutNet format.  Put
it under `datasets/hypercutnet/{ibm,titan}` or set `IBM_GRAPH_ROOT` and
`TITAN_GRAPH_ROOT` explicitly.

## Requirements

Tested target platform: 64-bit Linux.  Install Conda (or Mamba), Julia 1.10+
and a CMake/C++ toolchain that satisfies the OpenROAD dependencies.  A CPU-only
Python environment is supplied; CUDA is optional.

## Installation

From the HierPlaceFPGA repository root:

```bash
cd ML-SpecPart

conda env create -f HyperCutNet/environment-cpu.yml
conda activate gnn_design_cpu

julia --project=SpecPart -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'

./TritonPart/rebuild_par.sh all "$(nproc)"
```

The expected OpenROAD executable is `TritonPart/build/src/openroad`.  If you
built it elsewhere, use:

```bash
export SPECPART_OPENROAD_BIN=/absolute/path/to/openroad
```

Some systems require extra OpenROAD system libraries.  Follow the dependency
instructions in `TritonPart/OpenROAD/README.md` before building.  If a custom
GCC/Boost installation is needed, provide its prefix without modifying source:

```bash
GCC13_PREFIX=/path/to/toolchain ./TritonPart/rebuild_par.sh all "$(nproc)"
```

## Verify installation

Run this before launching an experiment:

```bash
cd ML-SpecPart
INFER_PYTHON="$(command -v python)" \
JULIA_BIN="$(command -v julia)" \
bash tools/preflight_check.sh
```

The preflight check verifies model files, Python packages, Julia packages, and
OpenROAD.  A warning about absent graph directories is expected until you
download or prepare inference graphs.

## Quick smoke test

After preflight succeeds, the following runs one released checkpoint on the
small bundled TritonPart input.  It verifies HGR conversion, GNN inference and
guided partitioning; it does not run the three-model Cut-Overlay stage.

```bash
cd ML-SpecPart
./tools/run_guided_partition.sh \
  --checkpoint checkpoints/titan11_TritonPart_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth \
  TritonPart/test/sample.hgr
```

Successful execution creates `outputs/guided_run/cut_prob.txt` and an OpenROAD
log.  Use `--workdir /path/to/new-output` to retain results from multiple runs.

## Single-case three-model flow

After preparing HyperCutNet graph directories, run one benchmark and one UB:

```bash
cd ML-SpecPart

IBM_GRAPH_ROOT="$PWD/datasets/hypercutnet/ibm" \
TITAN_GRAPH_ROOT="$PWD/datasets/hypercutnet/titan" \
INFER_PYTHON="$(command -v python)" \
NUM_SEEDS=5 \
SEED_WORKERS=5 \
JULIA_THREADS=1 \
bash tools/run_three_models_single_graph_single_ub_cutoverlay.sh \
  denoise 1
```

The result is written below
`experiments_revision/three_models_single_graph_single_ub/`.  The final
partition and summary are, respectively:

```text
<run-root>/cutoverlay/parts/cutoverlay_three_models_ubXX.part.2
<run-root>/cutoverlay/cutoverlay_three_models_summary.csv
```

For the four Titan23 cases (`denoise`, `segmentation`, `stereo_vision`, and
`gsm_switch`) across UB 1--20, use:

```bash
CASE_WORKERS=4 NUM_SEEDS=5 SEED_WORKERS=5 JULIA_THREADS=1 \
bash tools/run_three_models_four_cases_ub01_20_cutoverlay.sh
```

## Training

Run training from `HyperCutNet` so local imports resolve correctly:

```bash
cd ML-SpecPart/HyperCutNet
python src/train.py \
  --data_root rawdata \
  --dataset_savepath dataset \
  --checkpoint example_run \
  --batch_size 4 --layers 3 --hidden_dim 128 --epochs 200 --lr 0.001
```

See `HyperCutNet/README.md` for the input text format and optional model
features.

## Reproducibility notes

- Do not rely on server-specific absolute paths; use the environment variables
  documented by the shell scripts.
- Keep generated outputs outside Git.  `.gitignore` covers standard build,
  cache, and experiment directories.
- The bundled checkpoints are small enough for ordinary Git.  Place future
  checkpoints larger than 100 MB in Git LFS or a release asset.
- The TritonPart/OpenROAD and SpecPart subcomponents retain their respective
  upstream licenses in their directories.
