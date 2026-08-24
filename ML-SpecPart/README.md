# ML-SpecPart

ML-SpecPart is the ML-guided hypergraph-partitioning component of
HierPlaceFPGA.  It combines HyperCutNet GNN inference, TritonPart guided
partitioning, and the Julia SpecPart Cut-Overlay implementation.

## Repository layout

```text
ML-SpecPart/
├── HyperCutNet/     # HyperCutNet GNN source code, configuration, training, and inference
├── TritonPart/      # TritonPart/OpenROAD source code and bundled hypergraph benchmarks
├── SpecPart/        # Julia implementation of the SpecPart Cut-Overlay stage
├── checkpoints/     # Released HyperCutNet model checkpoints and their saved arguments
└── tools/           # Data-conversion utilities and end-to-end orchestration scripts
```

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

Run training from `HyperCutNet` so local imports resolve correctly.  Set the
three variables below to paths appropriate for the local clone.  The checkpoint
name is an output directory name, not an absolute path.

```bash
cd ML-SpecPart/HyperCutNet

PYTHON_BIN="$(command -v python)"
DATA_ROOT="/path/to/training_rawdata"
CHECKPOINT_NAME="pin2net_gat_grouped"
CACHE_PREFIX="/path/to/cache/pin2net_gat_grouped"

"$PYTHON_BIN" src/train_grouped.py \
  --data_root "$DATA_ROOT" \
  --checkpoint "$CHECKPOINT_NAME" \
  --dataset_savepath "$CACHE_PREFIX" \
  --batch_size 5 \
  --hidden_dim 128 \
  --layers 3 \
  --epochs 100 \
  --lr 0.0001 \
  --use_pagerank \
  --pin_struct_feat_mode hetero \
  --prune_overlap_topk 50 \
  --normalize_overlap_weights \
  --use_ubfactor \
  --ub_isolate \
  --ub_max 20 \
  --pin2net_type gat \
  --pin2net_gat_heads 4 \
  --pin2net_gat_chunk_nets 30000 \
  --net2net_type graphconv \
  --net2pin_type graphconv
```

The command writes the checkpoint, saved arguments, and logs to
`checkpoints/<CHECKPOINT_NAME>/`.  `CACHE_PREFIX` creates a pair of cached
dataset files (`.design.bin` and `.solinfos.pt`).  Use a new cache prefix if
any graph-construction option changes, such as PageRank, structural-feature
mode, or overlap pruning.

`--batch_size 5` is the number of solutions processed per design group, rather
than the number of unrelated graphs.  Add `--grouped_encode_once` only when a
single GNN encoding per design group is desired; it changes the optimizer-step
granularity.

See `HyperCutNet/README.md` for the input text format and optional model
features.
