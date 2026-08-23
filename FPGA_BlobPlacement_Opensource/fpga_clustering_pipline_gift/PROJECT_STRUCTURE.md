# FPGA Clustering Pipeline (GiFt) - Project Structure Document

> **Maintained by**: Claude Code (auto-updated with each technical change)
> **Last updated**: 2026-04-04
> **Main entry**: `run_complete_flow_with_json.py`

---

## 1. Project Overview

This project implements a **hierarchical FPGA placement pipeline** that improves
placement quality by combining graph-based clustering with analytical placement.
The core idea: cluster tightly-connected cells together, place clusters first,
then refine individual cell positions.

### Algorithm Pipeline (5 Phases)

```
Phase 1: Clustering      Phase 2: Cluster Placement    Phase 3: Net Reweight
┌────────────────┐       ┌─────────────────────┐       ┌──────────────────┐
│ Louvain → GIFT │──────>│ Build cluster hyper- │──────>│ Classify nets by │
│ → SpecPart     │       │ graph → DREAMPlace   │       │ cluster membership│
│ sub-clustering │       │ global placement     │       │ → assign weights  │
└────────────────┘       └─────────────────────┘       └──────────────────┘
                                    │                            │
                                    v                            v
                         Phase 4: Prepare Final         Phase 5: Final Run
                         ┌─────────────────────┐       ┌──────────────────┐
                         │ Scatter cells inside │──────>│ DREAMPlaceFPGA   │
                         │ clusters → init .pl  │       │ (optional auto)  │
                         │ → .aux, .wts, config │       └──────────────────┘
                         └─────────────────────┘
```

### Key Technologies
- **GIFT** (Graph-based FPGA Layout): spectral graph filter for initial layout
- **SpecPart**: supervised spectral hypergraph partitioning (Julia backend)
- **DREAMPlaceFPGA**: analytical FPGA placement engine (Nesterov optimizer)
- **Louvain**: community detection for initial coarse clustering

### 2026-03-30 Universal-Parameter Search Status (HPWL-Oriented)

#### Candidate source and experiment roots
- Candidate pool (from tuner logs 20260325/20260326):
  - `k_specpart_experiment/universal_search_20260331/candidates_v1/`
- Single-design screening (FPGA08, A/B/C/D):
  - `k_specpart_experiment/universal_search_20260331/screen_s1_fpga08/`
- Cross-design A/C comparison (focus4):
  - `k_specpart_experiment/universal_search_20260331/screen_s2_focus4_ac/`
  - summary: `focus4_ac_compare.json`
- Full 12-design validation (chosen winner, in progress):
  - `k_specpart_experiment/universal_search_20260331/final_all12_a/`

#### Focus4 (FPGA08/09/11/12) A vs C conclusion
Using the same extraction rule (last valid `iter ... HPWL ... Overflow` line in
`4_final_input/final_placement.log`):

- FPGA08: `C` better (`6,893,992` vs `6,919,264`)
- FPGA09: `A` better (`8,830,691` vs `8,832,406`)
- FPGA11: `A` better (`9,298,320` vs `9,397,140`)
- FPGA12: `C` better (`4,575,748` vs `4,584,927`)

Win-count is 2:2, but average HPWL over focus4 favors `A` slightly
(`A_over_C = 0.997774896...`, about 0.22% better on mean HPWL). Therefore
`cand_a_best_per_design` is selected as the current universal candidate for
full 12-design validation.

#### Selected universal candidate (current best)
File:
- `k_specpart_experiment/universal_search_20260331/candidates_v1/cand_a_best_per_design.json`

Key effective parameters (from generated run config):
- `clustering.specpart_mode = gift_then_spectral`
- `clustering.min_cluster_size = 337`
- `clustering.resolution = 1.062341388894038`
- `clustering.gift_scale = 0.599632013883368`
- `clustering.max_fanout = 150`
- `final_placement.final_iteration = 2000`
- `final_placement.learning_rate = 0.013080584886744205`
- `final_placement.gamma = 6.809759346743754`
- `final_placement.density_weight = 79999999.99999993`
- `final_placement.random_seed = 7116`
- `net_reweighting.intra_sub = 1.4423860832213171`
- `net_reweighting.intra = 1.1532243716426578`
- `net_reweighting.inter = 0.7248875225454047`

---

## 2. Directory Layout

```
fpga_clustering_pipline_gift/
├── run_complete_flow_with_json.py    # ★ MAIN ENTRY POINT
│
├── ─── Core Pipeline Modules ───
│   ├── fpga_clustering_pipeline_gift.py   # Phase 1: Louvain + GIFT clustering
│   ├── main_pipeline_with_viz.py          # Phase 1 orchestrator (with SpecPart + viz)
│   ├── gift_specpart_complete.py          # GIFT + SpecPart complete integration (Julia)
│   ├── cluster_placement_integration.py   # Phase 2: cluster-level placement
│   ├── net_reweighting_integration.py     # Phase 3: net weight assignment
│   └── visualization_clustering.py        # Visualization: HTML/PNG generation
│
├── ─── Batch / Parallel Runners ───
│   ├── batch_run_complete_flow.py         # Multi-design batch runner
│   ├── parallel_run_flow.py               # Parallel stages across designs
│   ├── parallel_run_flow_enhanced.py      # Enhanced parallel runner
│   └── run_stability_experiment.py        # Seed stability experiment
│
├── ─── Analysis / Diagnostics ───
│   ├── analyze_fanout.py                  # Net fanout distribution analysis
│   ├── plot_displacement.py               # Cell displacement plotting
│   ├── subcluster_span_analysis.py        # Sub-cluster span metrics
│   ├── subcluster_span_integration.py     # Span analysis integration
│   ├── diagnose.py                        # Pipeline diagnostic tool
│   └── verify_applied_fixes.py            # Regression verification
│
├── ─── Historical / Backup Versions ───
│   ├── *0313*.py, *02*.py, *01*.py        # Date-stamped backups
│   ├── *_patched*.py                      # Patched variants
│   └── *_nolog*.py                        # No-logging variants
│
├── tools/
│   ├── DREAMPlaceFPGA/                    # ★ ACTIVE placement engine (modified)
│   │   ├── dreamplacefpga/
│   │   │   ├── Placer.py                  # Entry: __main__ → placeFPGA()
│   │   │   ├── BasicPlace.py             # ★ Init placement + seed control
│   │   │   ├── NonLinearPlace.py          # Nesterov global placement loop
│   │   │   ├── PlaceDB.py                # Bookshelf parser + placement DB
│   │   │   ├── PlaceObj.py               # Objective (HPWL + density + timing)
│   │   │   ├── Params.py                 # JSON config parser
│   │   │   ├── EvalMetrics.py            # HPWL / overflow evaluation
│   │   │   ├── NesterovAcceleratedGradientOptimizer.py
│   │   │   ├── TrajectoryTrace.py        # Cell movement tracing
│   │   │   ├── plot_placement_metrics.py  # Post-run metrics plotting
│   │   │   └── ops/                      # C++/CUDA placement operators
│   │   │       ├── electric_potential/    # Density smoothing (ePlace)
│   │   │       ├── weighted_average_wirelength/  # WAE wirelength
│   │   │       ├── hpwl/                 # Half-perimeter wirelength
│   │   │       ├── lut_ff_legalization/  # FPGA-specific legalization
│   │   │       ├── dsp_ram_legalization/ # DSP/RAM column legalization
│   │   │       ├── pin_utilization/      # Pin density estimation
│   │   │       ├── rudy/                 # Routing utilization estimation
│   │   │       ├── move_boundary/        # Boundary constraint
│   │   │       └── ...                   # ~25 operator modules total
│   │   └── build/                        # Compiled C++/CUDA extensions
│   │
│   ├── DREAMPlaceFPGA copy/              # Backup copy (unused)
│   └── DREAMPlaceFPGA-MP/                # Multi-process variant (unused)
│
├── data/
│   ├── ispd2016/                          # ISPD 2016 benchmarks
│   │   ├── FPGA01/ .. FPGA12/            # Each: design.{aux,nodes,nets,pl,scl,lib,wts}
│   └── ispd2017/                          # ISPD 2017 benchmarks
│
├── logs_tuner_*/                          # Hyperparameter tuning results
│   ├── configs.json                       # Tuner config space
│   ├── results.json                       # Tuner results
│   └── run-N_*/                           # Individual run outputs
│       └── params.json                    # Best parameters
│
└── stability_experiment_results/          # Seed variation experiments
    └── seed_N/
        ├── 1_clustering/                  # Shared across seeds
        ├── 2_cluster_placement/           # Per-seed cluster DREAMPlace
        ├── 3_net_reweighting/             # Shared across seeds
        └── 4_final_input/                 # Per-seed final DREAMPlace
```

---

## 3. Core Modules - Detailed Reference

### 3.1 `run_complete_flow_with_json.py` (Main Entry)

**Role**: Orchestrates the full 5-phase pipeline. Accepts parameters via CLI
args, JSON config file, or both (CLI overrides JSON).

**Key function**: `run_complete_flow(benchmark_dir, output_base_dir, ...)`

**Output directory structure**:
```
output_dir/
├── 1_clustering/          # cluster_layouts.json, clustering_results.json
├── 2_cluster_placement/   # cluster_placement/ subdir with DREAMPlace files
├── 3_net_reweighting/     # design.wts (net weights)
└── 4_final_input/         # Final DREAMPlace input: .aux, .nodes, .nets,
                           #   .pl, .scl, .lib, .wts, .weights,
                           #   movable_init.pl, dreamplace_config.json
```

**JSON config support**: `--params_json path.json`
- Flat key-value: `{"min_cluster_size": 100, "gpu": 1}`
- Sectioned: `{"clustering": {...}, "final_placement": {...}}`
- Schema-like: `{"gpu": {"default": 1, "type": "int"}}`

---

### 3.2 `fpga_clustering_pipeline_gift.py` (Phase 1 Core)

**Role**: Louvain clustering + GIFT layout. The foundational clustering module.

#### Classes

| Class | Purpose |
|-------|---------|
| `GiFt` | Graph spectral filter. Two modes: `train(sigma)` for low-pass D^{-0.5}(A+σI)D^{-0.5}, `new_filter_train()` for Laplacian (λ_max·I - L)/λ_max |
| `GIFTInterface` | High-level GIFT wrapper. `run_gift_layout()` applies mixed-frequency filter (0.2×low + 0.7×mid + 0.1×high) to get node x/y positions |
| `FPGABookshelfParser` | Parses all Bookshelf files: `.aux`, `.nodes`, `.nets`, `.pl`, `.scl`, `.lib`, `.macros`, `.cascade_shape`. Builds adjacency matrix |
| `LouvainClusterer` | Louvain community detection with `enforce_max_cluster_size()` for recursive splitting |
| `SpecPartInterface` | Generates SpecPart input files (hMETIS format + GIFT features) |
| `FPGAClusteringPipeline` | Main pipeline: parse → locked clusters (cascade+macro) → Louvain → merge small → GIFT layout |

#### Important Data Structures

```python
# cluster_layouts: Dict[int, Dict]
{
    cluster_id: {
        'node_indices': [int],       # Global node indices
        'positions': np.ndarray,     # (N, 2) GIFT x/y positions
        'x_features': np.ndarray,    # GIFT x-feature vector
        'y_features': np.ndarray,    # GIFT y-feature vector
        'locked': bool,              # True for cascade/macro clusters
        'lock_type': str             # 'cascade' | 'macro'
    }
}

# clustering_results: Dict[int, Dict]  (from SpecPart sub-clustering)
{
    cluster_id: {
        'clusters': [[int, ...], ...],  # Sub-cluster node indices (global)
        'num_sub_clusters': int,
        'locked': bool
    }
}
```

#### Locked Cluster Handling
- **Cascade chains**: BRAM cells linked via CASCADE_OUT/CASCADE_IN pins
- **Macro clusters**: DSP/BRAM cells + N-hop neighbors (`macro_neighbor_depth`)
- Locked clusters skip Louvain splitting and SpecPart partitioning

---

### 3.3 `main_pipeline_with_viz.py` (Phase 1 Orchestrator)

**Role**: `EnhancedFPGAPipeline` wraps `FPGAClusteringPipeline` and adds
SpecPart sub-clustering + visualization.

**Key class**: `EnhancedFPGAPipeline(benchmark_dir, output_dir, cluster_random_seed)`

**SpecPart execution**: `_run_cutoverlay_clustering()` batches cluster jobs
and dispatches them to `GIFTSpecPartPipeline.batch_k_specpart()` for parallel
Julia execution.
**No-GIFT mode**: `specpart_mode="louvain_kway"` disables Phase-1 GIFT layout and passes no feature file to Julia, so K_SpecPart runs directly on Louvain clusters while preserving parallel sub-batch isolation.

**Worker parallelism**: Uses `ProcessPoolExecutor` with `_cutoverlay_worker()`
for CPU-parallel SpecPart runs.

---

### 3.4 `gift_specpart_complete.py` (GIFT + SpecPart Integration)

**Role**: Complete GIFT + SpecPart pipeline with Julia backend for k-way
hypergraph partitioning.

#### Key Class: `GIFTSpecPartPipeline`

**Julia backend**: Calls `julia -e "..."` as subprocess. The Julia code:
1. Reads hMETIS-format hypergraph
2. Uses GIFT x/y features for initial spectral embedding
3. Builds bisection trees (`GenTrees`)
4. Performs tree partitioning + overlay clustering
5. Returns partition assignment

**Three SpecPart modes** (`specpart_mode` parameter):
- `"gift_single"`: One-shot GIFT tree partition + overlay (fast, no iteration)
- `"gift_then_spectral"`: First iteration uses GIFT features, subsequent
  iterations use standard spectral `solve_eigs` (more refined)
- `"louvain_kway"`: Disables GIFT layout/features; runs full K_SpecPart directly on Louvain clusters (parallel Julia sub-batches with isolated working dirs)

**Batch API**: `batch_k_specpart(batch_jobs, ...)` runs multiple cluster
partitionings in parallel Julia workers.

---

### 3.5 `cluster_placement_integration.py` (Phase 2)

**Role**: Build cluster-level hypergraph and run DREAMPlaceFPGA to place
cluster virtual nodes, then scatter individual cells within clusters.

#### Classes

| Class | Purpose |
|-------|---------|
| `ClusterHypergraphBuilder` | Converts clustering results into DREAMPlace Bookshelf format: each sub-cluster becomes a virtual node; inter-cluster nets become hyperedges. Handles fixed nodes (IO/macro) |
| `ClusterPlacementGenerator` | Generates `.nodes`, `.nets`, `.pl`, `.scl`, `.aux`, `.weights`, `.wts` for cluster-level DREAMPlace run. Controls `cluster_node_sizes.json` for custom node sizing |
| `ClusterPlacementIntegration` | Full pipeline: parse benchmark → build hypergraph → run DREAMPlace → scatter cells → generate `movable_init.pl` + `design.pl` |

#### Cell Scattering (inside clusters)
After cluster placement, individual cells are distributed within each cluster's
region using one of:
- `"gaussian_circle"`: 2D Gaussian with `sigma_ratio` controlling spread
- `"uniform_rect"`: Uniform random within bounding rectangle

**Output**: `movable_init.pl` (movable nodes only) + `design.pl` (fixed nodes)

---

### 3.6 `net_reweighting_integration.py` (Phase 3)

**Role**: Adjust net weights based on clustering to guide final placement.

#### Class: `NetReweightingIntegration`

**Net classification** (`classify_net()`):
| Category | Condition | Default Weight |
|----------|-----------|----------------|
| `intra_subcluster` | All pins in same sub-cluster | 1.5 (tighter) |
| `intra_cluster` | All pins in same Louvain cluster | 1.0 (neutral) |
| `inter_cluster` | Pins span multiple clusters | 0.8 (relaxed) |
| `unknown` | Pins not in any cluster | 1.0 |

**Output**: `.wts` file (one weight per net, matching `.nets` order)

---

### 3.7 `visualization_clustering.py`

**Role**: Generate interactive HTML (Plotly) and PNG visualizations.

#### Key Classes/Functions
- `SCLParser`: Parse `.scl` files for chip geometry and IO locations
- `generate_interactive_html()`: Full interactive plot with nodes, edges,
  fixed nodes, IO sites, displacement arrows
- `visualize_gift_pipeline()`: Before/after GIFT comparison per cluster
- `run_specpart_clustering_with_visualization()`: Visualize SpecPart results

---

## 4. DREAMPlaceFPGA Integration

### Execution Model
DREAMPlaceFPGA runs as a **subprocess** in both cluster and final placement:
```python
cmd = f"python {placer_script} {config_json}"
subprocess.run(cmd, shell=True, cwd=output_dir, ...)
```

### Key Files (Modified from upstream)

| File | Modifications |
|------|--------------|
| `BasicPlace.py` | ★ Seed control: `np.random.seed(params.random_seed)` instead of hardcoded `manualSeed=0`. Init placement from file (`init_placement_file`). Custom node sizes (`cluster_node_sizes.json`). Filler cell init with subregion awareness |
| `NonLinearPlace.py` | Debug position dumps before/after global placement |
| `PlaceObj.py` | Net weight annealing (`net_weight_anneal_iters`). Weighted HPWL reporting |
| `Placer.py` | `placeFPGA()`: custom node size application via `apply_custom_node_sizes_from_json()`. `TrajectoryTrace` integration |
| `Params.py` | Extended JSON parameters: `init_placement_file`, `cluster_node_size_file`, `trace_cells_*`, `net_weight_anneal_iters` |
| `TrajectoryTrace.py` | New: tracks per-cell movement trajectories across iterations |

### Config JSON Structure (Final Placement)
```json
{
    "aux_input": "design.aux",
    "init_placement_file": "movable_init.pl",
    "net_weight_file": "design.weights",
    "gpu": 0,
    "global_place_stages": [{
        "num_bins_x": 512, "num_bins_y": 512,
        "iteration": 2000, "learning_rate": 0.01,
        "wirelength": "weighted_average",
        "optimizer": "nesterov",
        "net_weight_anneal_iters": 600
    }],
    "random_seed": 42,
    "random_center_init_flag": 0,
    "deterministic_flag": 1,
    "density_weight": 8.0,
    "gamma": 8.28,
    "routability_opt_flag": 1
}
```

### ⚠ Known Issue: DREAMPlace Path Mismatch
There are **two copies** of DREAMPlaceFPGA:
- `/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/` — OLD version
  (`manualSeed = 0` hardcoded, ignores `params.random_seed`)
- `/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/`
  — FIXED version (uses `params.random_seed`)

The experiment config's `dreamplace_path` must point to the **inner** (fixed)
copy for seed-controlled reproducibility.

---

## 5. Bookshelf File Format Reference

The pipeline uses Bookshelf format for DREAMPlaceFPGA I/O:

| File | Contents |
|------|----------|
| `.aux` | Master: lists all design files |
| `.nodes` | Cell names + types (LUT6, FF, DSP48E2, RAMB36E2, ...) |
| `.nets` | Hypergraph: `net_name degree` → `pin_name {B\|O} x_off y_off` |
| `.pl` | Placement: `inst_name x y z [FIXED]` |
| `.scl` | Site map: SITE definitions, RESOURCES, SITEMAP grid |
| `.lib` | Cell library: pin definitions per cell type |
| `.wts` | Net weights: one float per net (optional) |
| `.weights` | Same as `.wts` (renamed for DREAMPlace compatibility) |
| `.macros` | Macro instance names |
| `.cascade_shape` | BRAM cascade chain templates or instance groups |
| `.regions` | Placement region constraints (optional) |

---

## 6. Key Parameters & Tuning Knobs

### Clustering (Phase 1)
| Parameter | Default | Effect |
|-----------|---------|--------|
| `min_cluster_size` | 50 | Clusters smaller than this are merged into neighbors |
| `max_cluster_size` | None | Clusters larger than this are recursively split |
| `louvain_resolution` | 1.0 | Higher → more clusters, lower → fewer |
| `gift_scale` | 0.5 | Initial random position spread for GIFT |
| `macro_neighbor_depth` | -1 | -1=disabled, 0=macro only, N=N-hop neighbors locked |
| `specpart_mode` | `gift_then_spectral` | `gift_single` (fast) vs `gift_then_spectral` (refined) vs `louvain_kway` (no GIFT, direct Louvain→K_SpecPart) |
| `specpart_ub_factor` | 10 | Partition imbalance tolerance (%) |
| `specpart_num_seeds` | 5 | Number of perturbed seeds, pick best cutsize |
| `specpart_num_workers` | 15 | Parallel Julia worker count |

### Cluster Placement (Phase 2)
| Parameter | Default | Effect |
|-----------|---------|--------|
| `cluster_iteration` | 1000 | DREAMPlace iterations for cluster placement |
| `utilization` | 0.8 | Cluster virtual node size = utilization × site area |
| `cluster_base_weight` | 0.1 | Base net weight for cluster-level nets |
| `cluster_fixed_cluster_weight` | 5.0 | Boosted weight for fixed↔cluster nets |
| `sigma_ratio` | 0.95 | Gaussian scatter spread within clusters |
| `scatter_mode` | `gaussian_circle` | Cell distribution mode inside clusters |

### Net Reweighting (Phase 3)
| Parameter | Default | Effect |
|-----------|---------|--------|
| `intra_subcluster_weight` | 1.5 | Tighter packing within sub-clusters |
| `intra_cluster_weight` | 1.0 | Neutral within Louvain cluster |
| `inter_cluster_weight` | 0.8 | Relaxed between clusters |

### Final Placement (Phase 4/5)
| Parameter | Default | Effect |
|-----------|---------|--------|
| `final_iteration` | 2000 | DREAMPlace iterations |
| `learning_rate` | 0.01 | Nesterov optimizer step size |
| `density_weight` | 0.01 | Density penalty strength |
| `gamma` | 0.8 | Wirelength smoothing parameter |
| `net_weight_anneal_iters` | 0 | Gradually anneal net weights to 1.0 (0=disabled) |
| `routability_opt_flag` | 1 | Enable routability optimization |
| `random_seed` | 1000 | DREAMPlace random seed |
| `deterministic_flag` | 1 | Deterministic ops (slower but reproducible) |

---

## 7. Data Flow Diagram

```
Benchmark (.aux .nodes .nets .pl .scl .lib)
    │
    ▼
FPGABookshelfParser.parse_*()
    │
    ├──> adjacency_matrix (scipy sparse)
    ├──> node_names[], node_types[], nets{}
    ├──> fixed_positions{} (from .pl FIXED)
    └──> chip geometry (from .scl SITEMAP)
         │
         ▼
LouvainClusterer.run_clustering()
    │
    ├──> partition: node_id → cluster_id
    └──> locked_clusters (cascade/macro)
         │
         ▼
GIFTInterface.run_gift_layout()  (per cluster)
    │
    ├──> positions: (N, 2) x/y per node
    └──> x_features, y_features (spectral)
         │
         ▼
GIFTSpecPartPipeline.batch_k_specpart()  (Julia subprocess)
    │
    └──> clustering_results: cluster_id → {clusters: [[sub-cluster nodes]]}
         │
         ▼
ClusterPlacementIntegration.run_cluster_placement()
    │
    ├──> Bookshelf files for cluster-level design
    ├──> DREAMPlaceFPGA subprocess → cluster positions
    └──> generate_initial_placement() → movable_init.pl + design.pl
         │
         ▼
NetReweightingIntegration.run()
    │
    └──> design.wts / design.weights (per-net weights)
         │
         ▼
4_final_input/  (complete DREAMPlaceFPGA input)
    │
    ▼
DREAMPlaceFPGA Placer.py → results/design.gp.pl (final placement)
```

---

## 8. Adjacency Matrix & GIFT Filter — Comparison with Original GIFT

### 8.1 Adjacency Matrix Construction (`build_adjacency_matrix()`)

**Location**: `fpga_clustering_pipeline_gift.py:774-852`

For each net with `k` pins, the pipeline uses **clique expansion** (complete graph):
- Creates all `k(k-1)/2` undirected edges (both directions stored)
- Weight per edge: `2.0 / k`
- Nets with <2 pins are skipped (trivial)
- **Filtering**: clock nets >50 pins skipped; ALL nets >500 pins skipped

This adjacency matrix is used for **both** Louvain clustering and GIFT layout.

### 8.2 Original GIFT (GiFt_ICCAD24_opensource) Input

The original GIFT implementation uses the **same weight formula**:

```python
# utils/util.py:96-126  cluster_level_connectivity_sparse()
for x in subnetlist[flag]:
    for y in subnetlist[flag]:
        if xx != yy:
            group_level_feature[xx, yy] += 2 / node_num_in_net
```

Key differences from our project:

| Aspect | Original GIFT | This Project |
|--------|--------------|--------------|
| Weight formula | `2/k` (clique) | `2/k` (clique) — **identical** |
| Mixed filter | `0.2·low + 0.7·mid + 0.1·high` | `0.2·low + 0.7·mid + 0.1·high` — **identical** |
| Net filtering | Only skips `ispd_clk` by name | Skips clock nets >50 pins + ALL nets >500 pins |
| Graph scope | Full chip (movable + IO pads) | Per-cluster induced subgraph |
| Data format | DEF/LEF (ASIC benchmarks) | Bookshelf (FPGA benchmarks) |
| Recursive split | GIFT → FM partition → virtual pins at cut line | Louvain → GIFT → SpecPart |
| Cross-partition | Virtual pin nodes preserve inter-partition edges | Induced subgraph — cross-cluster edges truncated |

### 8.3 Weight Formula Properties

For a net with `k` pins, the clique expansion produces:
- `k(k-1)/2` undirected edges, each with weight `2/k`
- Total weight contribution per net = `k(k-1)/2 × 2/k = k-1`

This means a 500-pin net contributes total weight 499, while a 2-pin net contributes 1.
Large nets have disproportionate influence on adjacency structure and Louvain modularity.

**Possible alternatives** (not yet implemented):
- `1/(k-1)`: constant total weight per net (=1)
- `2/(k*(k-1))`: constant total weight per net (=1)

---

## 9. High-Fanout Net Handling (>500 Pins) — Complete Flow Trace

### 9.1 Overview

Nets with >500 pins are **hardcoded-filtered** during adjacency matrix construction
(line 815-817), but are **not permanently removed** from the design. Here is their
fate at each pipeline stage:

```
Stage              >500-pin Nets                  Nodes Only in >500-pin Nets
─────────────────  ─────────────────────────────  ──────────────────────────────
1. Adj Matrix      EXCLUDED (line 815)            Become degree-0 (isolated)
2. Isolated Det.   N/A                            Detected & excluded from Louvain
3. Louvain         Not in edges                   NOT sent to Louvain
4. GIFT Layout     Not in sub_adj edges           NOT in any cluster yet
5. SpecPart        Subject to own filtering       NOT in any cluster yet
6. Delayed Assign  Used for scoring (1/fanout)    Assigned to best cluster by score
7. Cluster Hyper.  RE-EXAMINED (line 448)          In clusters, contribute edges
8. Net Reweight    ALL nets classified (line 310)  Classified by cluster membership
9. Final Place     Optionally filtered (max_fanout) Placed within clusters
```

### 9.2 Isolated Node Detection & Delayed Assignment

After `build_adjacency_matrix()` filters out nets with >500 pins, nodes that
*only* appear in those nets become degree-0 (isolated) in the adjacency matrix.
These nodes are now handled with a two-phase approach:

**Phase A — Detection & Exclusion** (`fpga_clustering_pipeline_gift.py`, in `run_pipeline()`):
```python
degrees = np.array(self.adj_matrix.sum(axis=1)).flatten()
candidate_active = all_nodes - used_nodes
isolated_nodes = {v for v in candidate_active if degrees[v] == 0}
active_nodes = sorted(candidate_active - isolated_nodes)
self.isolated_nodes = isolated_nodes
```
Isolated nodes are excluded from Louvain entirely. They do not participate in
community detection, merge-small, enforce-max-size, GIFT layout, or SpecPart.

**Phase B — Delayed Assignment** (`delayed_assign_isolated_nodes()`, called after
Phase 1 completes — i.e., after SpecPart/k_specpart):

For each unassigned node `v`:
1. Only examines nets with fanout >= 500 (the same threshold used in adjacency filtering)
2. Scores each candidate cluster `c` by: `score(c) += 1/fanout(e)` for each
   high-fanout net `e` connecting `v` to a node already in cluster `c`
   (each cluster counted once per net)
3. Assigns `v` to the cluster with the highest score
4. **Fallback**: if no high-fanout net connects `v` to any clustered node,
   assigns to the largest cluster

The inverse-fanout weight `alpha(e) = 1/fanout(e)` ensures that moderately-large nets
(e.g., 500-pin) contribute more signal than extremely large nets (e.g., 5000-pin).

**Call sites**:
- `main_pipeline_with_viz.py`: called after `_run_cutoverlay_clustering()` (SpecPart path)
- `run_complete_flow_with_json.py`: called after `SimplePipeline` creation (no-SpecPart path)

### 9.3 Stage Details

**Stage 1 — Adjacency Matrix** (`fpga_clustering_pipeline_gift.py:815-817`):
```python
if len(node_indices) > 500:
    ignored_nets += 1
    continue
```
>500-pin nets produce zero edges. Nodes appearing *only* in such nets become
isolated (degree 0) in the sparse adjacency matrix.

**Stage 2 — Isolated Node Detection** (`fpga_clustering_pipeline_gift.py`, `run_pipeline()`):
Degree-0 nodes are detected and excluded from `active_nodes` before Louvain.
They are stored in `self.isolated_nodes` for delayed assignment after Phase 1.

**Stage 3 — Louvain Clustering**:
Only connected (degree > 0) non-locked nodes are passed to Louvain.
Isolated nodes do not participate in community detection.

**Stage 4 — Small Cluster Merging** (`fpga_clustering_pipeline_gift.py:1272-1374`):
```python
# _merge_small_louvain_clusters_into_large()
```
Small clusters of connected nodes are merged into neighboring clusters.
Isolated nodes are not involved (they were excluded before Louvain).

**Stage 7 — Cluster Hypergraph** (`cluster_placement_integration.py:448`):
```python
for net_name, pins in self.nets.items():  # ALL nets, no 500-pin filter
```
The cluster-level hypergraph builder iterates **all original nets** (including >500-pin).
However, only pins whose nodes are in `node_to_subcluster` contribute edges.
An additional `max_fanout` parameter (default: None/0 = disabled) can further filter here.

**Stage 8 — Net Reweighting** (`net_reweighting_integration.py:310-315`):
```python
for net_name in self.net_names_ordered:  # ALL nets
    net_nodes = self.nets[net_name]
    net_type = self.classify_net(net_nodes)  # classifies by cluster membership
```
All nets (including >500-pin) get classified and weighted. No fanout filtering here.

**Stage 9 — Final Placement** (`cluster_placement_integration.py:1875-1907`):
Optional `max_fanout` parameter can filter nets before final DREAMPlace run.
Default is 0 (disabled) — so by default, **all nets go to DREAMPlace**.

### 9.4 Remaining Considerations

1. **No node coverage assertion**: The code prints `total_nodes` in debug output
   but does not verify it equals `self.parser.num_nodes`. Silent node loss is possible.

2. **Asymmetric filtering**: The 500-pin threshold is hardcoded in `build_adjacency_matrix()`
   but not parameterized. Cluster placement and net reweighting see ALL nets, creating
   an inconsistency — clustering ignores these nets but downstream stages use them.

---

## 10. Cross-Design Unified Params (2026-03-28)

To run one parameter set for all ISPD2016 designs (`FPGA01`~`FPGA12`), use:

- `global_unified_params_20260328.json`
- `global_unified_params_20260328_timeoutfix.json` (same tuned params + larger SpecPart timeout controls for heavy designs)
- `global_unified_params_20260330_hpwlopt_v1.json` (HPWL-oriented v1 update from 2026-03-30 final-placement sweeps)
- path: `fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/global_unified_params_20260328.json`
- path: `fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/global_unified_params_20260330_hpwlopt_v1.json`

This config keeps `specpart_mode="louvain_kway"` and applies one fixed parameter
vector across all designs.

```json
{
  "min_cluster_size": 543,
  "resolution": 0.944087373733923,
  "gift_scale": 0.572131381326489,
  "ub_factor": 23,
  "best_solns": 12,
  "max_cluster_size": 2750,
  "place_density_lb_addon": 1.3881326872734963,
  "sigma_ratio": 0.8483230432338384,
  "cluster_base_weight": 2.2175192293268156,
  "cluster_fixed_cluster_weight": 59.92264780659359,
  "max_fanout": 400,
  "intra_sub": 1.462664886900812,
  "intra": 0.8633828181347643,
  "inter": 0.8034363016117805,
  "learning_rate": 0.1302812594147706,
  "net_weight_anneal_iters": 50,
  "density_weight": 80.0,
  "gamma": 2.8415714240080323,
  "cluster_random_seed": 1674,
  "random_seed": 7116
}
```

`global_unified_params_20260330_hpwlopt_v1.json` updates only final-placement knobs
from the timeoutfix baseline:

```json
{
  "learning_rate": 0.024,
  "net_weight_anneal_iters": 400,
  "density_weight": 8000000.0,
  "gamma": 9.1
}
```

---

## 11. Change Log

| Date | Change | Files Affected |
|------|--------|---------------|
| 2026-04-04 | **Experiment Infra**: `run_universal_stability_search_v2.py` now enforces hard feasibility (`mean_cv_pct < baseline` + HPWL guardrail), applies deterministic feasible-first selection, runs layered adaptive rounds (`A/B/C`) with auto-expand steps, and emits `feasibility_report.json` + `search_round_summary.csv` | `run_universal_stability_search_v2.py`, `PROJECT_STRUCTURE.md` |
| 2026-04-02 | **Experiment Infra Fix**: Hardened `gp_noise_ratio=0` search orchestration: resume now treats final-placement traceback/NaN logs as `failed_existing` (not success), Round-1 search space shifted to conservative stability-focused ranges, and explicit `no_complete_candidate_debug.json` output when no full 12-design candidate is found | `k_specpart_experiment/universal_search_gp0_20260402/run_gp0_universal_optimization.py`, `PROJECT_STRUCTURE.md` |
| 2026-04-02 | **Experiment Infra**: Added isolated gp-noise optimization pipeline (`gp_noise_ratio=0` for final placement) with baseline/full-search/stability automation; keeps `specpart_mode=gift_then_spectral` and leaves main runner untouched | `run_complete_flow_with_json_gp0opt.py` (new copied runner), `k_specpart_experiment/universal_search_gp0_20260402/run_gp0_universal_optimization.py` (new), `PROJECT_STRUCTURE.md` |
| 2026-03-30 | **Experiment**: Added HPWL-oriented unified config `global_unified_params_20260330_hpwlopt_v1.json` (kept clustering/cluster-placement/net-reweighting unchanged; tuned final placement to `learning_rate=0.024`, `net_weight_anneal_iters=400`, `density_weight=8e6`, `gamma=9.1`) | `global_unified_params_20260330_hpwlopt_v1.json`, `PROJECT_STRUCTURE.md` |
| 2026-03-28 | **Experiment**: Added timeout-fixed batch config `global_unified_params_20260328_timeoutfix.json` (`specpart_timeout=21600`, `specpart_per_job_timeout=240`, `specpart_num_workers=3`) for cross-design full runs | `global_unified_params_20260328_timeoutfix.json`, `PROJECT_STRUCTURE.md` |
| 2026-03-28 | **Experiment**: Added cross-design unified parameter config `global_unified_params_20260328.json` and documented one-set-for-12-design run setup | `global_unified_params_20260328.json`, `PROJECT_STRUCTURE.md` |
| 2026-03-28 | **Feature**: Added `specpart_mode="louvain_kway"` — skip GIFT layout/features and run parallel full K_SpecPart directly on Louvain clusters; kept per-sub-batch isolated working directories to avoid file collisions | `fpga_clustering_pipeline_gift.py`, `main_pipeline_with_viz.py`, `run_complete_flow_with_json.py`, `PROJECT_STRUCTURE.md` |
| 2026-03-24 | **Feature**: Adaptive parameter selection — KNN-based auto-tuning from 12 benchmark profiles eliminates per-design BOHB tuning | `adaptive_params.py` (new), `adaptive_profiles.json` (new), `run_complete_flow_with_json.py`, `PROJECT_STRUCTURE.md` |
| 2026-03-22 | **Feature**: Isolated node delayed assignment — exclude degree-0 nodes from Louvain, assign post-Phase-1 using high-fanout net scoring with inverse-fanout weights | `fpga_clustering_pipeline_gift.py`, `main_pipeline_with_viz.py`, `run_complete_flow_with_json.py`, `PROJECT_STRUCTURE.md` |
| 2026-03-22 | **Doc**: Added original GIFT comparison (Section 8) and high-fanout net flow trace (Section 9) | `PROJECT_STRUCTURE.md` |
| 2026-03-21 | **Fix**: DREAMPlaceFPGA `BasicPlace.py` seed control — changed `manualSeed=0` to `params.random_seed` so cluster placement respects the configured seed | `tools/DREAMPlaceFPGA/dreamplacefpga/BasicPlace.py` |
| 2026-03-21 | **Doc**: Created this PROJECT_STRUCTURE.md | `PROJECT_STRUCTURE.md` |

---

## 12. Adaptive Parameter Selection

Automatically selects good pipeline parameters for a new design based on design
characteristics, eliminating the need for per-design BOHB tuning (50+ iterations).
目前，在新设计上运行管道需要通过 BOHB 进行大量的手动参数调优（每个基准测试超过 50 次迭代）。我们有 12 个基准的调优结果和最佳配置。目标是创建一个系统，能够根据设计特征自动选择好的参数，从而消除每个设计的调优需求。
设计特征空间（从所有 12 个 ISPD2016 基准提取）：
num_nodes：105K 到 1.1M
FF/LUT 比率：0.43 到 1.71
num_macros (DSP+BRAM)：0 到 1600
num_high_fanout_nets (>500)：21 到 141
所有基准都针对相同的 168x480 芯片结构。
来自调优器数据的关键见解：

一些参数有明显的设计规模趋势（例如，learning_rate 随着规模增大），而其他参数则较为嘈杂，但有稳健的中值范围（例如，intra_sub 始终在 1.1–1.9 之间）。我们对趋势参数使用 KNN 插值，对类别/噪声参数使用最近邻方法。

激活
JSON 键："adaptive": true 在 params_json 中启用自适应模式。
CLI 标志：--adaptive 也能生效。
优先顺序：CLI 参数 > 其他 JSON 键 > 自适应参数 > 硬编码默认值。
种子：cluster_random_seed 和 random_seed 从不由自适应设置——始终由用户控制。
方法：加权 K=3 最近邻插值

将 12 个已知基准的配置文件（设计特征 + 最佳调优参数）作为静态查找表存储。对于一个新设计：

快速解析设计以提取特征（num_nodes, num_LUT, num_FF, num_DSP, num_BRAM, num_high_fanout_nets）。
通过加权归一化欧几里得距离找到 K=3 个最接近的基准。
使用这些邻居的最佳参数进行逆距离加权平均。
类别参数（density_weight、max_fanout、max_cluster_size）只使用最近邻方法。
特征归一化与权重：
num_nodes / 1e6（权重 3.0）——主要的设计规模信号。
ff_lut_ratio（权重 1.0）——设计结构。
num_macros / 2000（权重 1.0）——宏复杂度。

Parameters covered (18 total, excluding seeds):                                                                                           │
│                                                                                                                                           │
│ ┌──────────────────────────────┬──────────────────────────┐                                                                               │
│ │          Parameter           │      Interpolation       │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ min_cluster_size             │ round(weighted avg)      │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ resolution                   │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ gift_scale                   │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ ub_factor                    │ round(weighted avg)      │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ best_solns                   │ round(weighted avg)      │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ max_cluster_size             │ nearest neighbor         │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ max_fanout                   │ nearest neighbor         │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ sigma_ratio                  │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ cluster_base_weight          │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ cluster_fixed_cluster_weight │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ place_density_lb_addon       │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ intra_sub                    │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ intra                        │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ inter                        │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ learning_rate                │ exp(weighted avg of log) │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ density_weight               │ nearest neighbor         │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ gamma                        │ weighted avg             │                                                                               │
│ ├──────────────────────────────┼──────────────────────────┤                                                                               │
│ │ net_weight_anneal_iters      │ round to nearest 50      │                                                                               │
│ └──────────────────────────────┴──────────────────────────┘       
### 12.1 How It Works

1. **Feature extraction** — lightweight parsing of `.nodes` and `.nets` to get
   `num_nodes`, `num_lut`, `num_ff`, `num_dsp`, `num_bram`, `num_hf_nets`.
2. **K=3 nearest neighbor lookup** — weighted Euclidean distance in feature space
   (`num_nodes/1e6 * 3`, `ff_lut_ratio`, `macros/2000`).
3. **Inverse-distance weighted interpolation** of best-tuned params from the 3
   nearest known benchmarks.  Categorical params (`density_weight`, `max_fanout`,
   `max_cluster_size`) use nearest-neighbor only.  `learning_rate` is interpolated
   in log-space.

### 12.2 Files

| File | Role |
|------|------|
| `adaptive_profiles.json` | Editable data: 12 benchmark profiles (features + best params). Add/update entries without code changes. |
| `adaptive_params.py` | Core logic: `extract_design_features()`, `compute_adaptive_params()`. Standalone smoke test via `python adaptive_params.py --benchmark_dir ...`. |
| `run_complete_flow_with_json.py` | Integration: `--adaptive` CLI flag or `"adaptive": true` in JSON enables adaptive mode. |

### 12.3 Activation

```bash
# Via CLI flag
python run_complete_flow_with_json.py --benchmark_dir data/ispd2016/FPGA03 --adaptive ...

# Via JSON config
python run_complete_flow_with_json.py --params_json '{"adaptive": true}' --benchmark_dir ...

# With overrides (gamma from JSON, everything else adaptive)
python run_complete_flow_with_json.py --params_json '{"adaptive": true, "gamma": 5.0}' ...
```

### 12.4 Priority Order

**CLI args > JSON keys > adaptive params > argparse defaults**

Seeds (`cluster_random_seed`, `random_seed`) are never set by adaptive.

### 12.5 Covered Parameters (18)

`min_cluster_size`, `resolution`, `gift_scale`, `ub_factor`, `best_solns`,
`max_cluster_size`, `max_fanout`, `sigma_ratio`, `cluster_base_weight`,
`cluster_fixed_cluster_weight`, `place_density_lb_addon`, `intra_sub`,
`intra`, `inter`, `learning_rate`, `density_weight`, `gamma`,
`net_weight_anneal_iters`.

### 12.6 Updating Profiles

Edit `adaptive_profiles.json` directly:
- **Update best params**: replace the `best_params` dict for a benchmark.
- **Add a new benchmark**: add a new key with `features` and `best_params`.
- **Custom path**: `--adaptive_profiles /path/to/custom.json`.

---

## 13. Environment

- **Python**: 3.8 (conda)
- **Julia**: 1.9.4 (for SpecPart backend)
- **PyTorch**: 1.7.1 (DREAMPlaceFPGA)
- **Key Python deps**: numpy, scipy, community (python-louvain), matplotlib, plotly
- **Required for Gurobi paths**: gurobipy + valid Gurobi license (Python ILP and SpecPart/Gurobi integration)
- **Benchmark format**: ISPD 2016/2017 FPGA placement benchmarks (Bookshelf)

两个 DREAMPlace 代码的差异分析与变差原因

  一、代码差异总结

  两个目录在 3 个核心文件 上存在差异（其余 50+ 文件完全一致）：

  ┌───────────────────┬─────────────────────────┐
  │       文件        │        变更类型         │
  ├───────────────────┼─────────────────────────┤
  │ BasicPlace.py     │ 算法修改 + 调试代码     │
  ├───────────────────┼─────────────────────────┤
  │ NonLinearPlace.py │ 重大算法修改 + 调试代码 │
  ├───────────────────┼─────────────────────────┤
  │ PlaceObj.py       │ 重大算法修改 + 调试代码 │
  └───────────────────┴─────────────────────────┘

  新目录还新增了 4 个文件（TrajectoryTrace.py, 两个备份文件, plot_placement_metrics_copy.py）。

  二、关键算法变更（非调试代码）

  变更1: Net Weight Annealing（网络权重退火）— 影响最大

  新代码 NonLinearPlace.py:186-230 新增了 cosine 退火机制：

  def anneal_net_weights(cur_iter):
      prog = min(1.0, t / float(anneal_iters))  # 0 -> 1
      s = 0.5 * (1.0 + math.cos(math.pi * prog))  # 1 -> 0
      nw.copy_(netw_delta).mul_(s).add_(1.0)  # w = 1 + (w0-1)*s

  这意味着 Phase 3 精心计算的 net weights（intra/inter cluster 权重）会在 placement 过程中被逐渐退火到 1.0。到 placement 结束时，所有 net weight 都变成 1.0，等于完全废掉了 net
  reweighting 的作用。旧代码不做退火，net weights 全程保持不变。


  变更2: HPWL 指标变更

  旧代码 PlaceObj.py:581：
  return getattr(m, "hpwl_weighted", m.hpwl)  # 用加权 HPWL

  新代码 PlaceObj.py:615-618：
  return m.hpwl  # 用未加权 HPWL

  Density weight 更新决策从基于 加权 HPWL 改为基于 原始 HPWL。这改变了优化动态。

  变更3: Random Seed 可配置化

  旧代码 BasicPlace.py:247：硬编码 manualSeed = 0

  新代码 BasicPlace.py:253-261：使用 params.random_seed

  变更4: 额外的梯度计算（Force Norm 日志）

  新代码 NonLinearPlace.py:391-396 每次迭代额外调用：
  wl_f, den_f = model.wl_density_force_norms(pos)

  这个函数 (PlaceObj.py:251-284) 做了额外的 forward + backward pass，可能在首次调用时改变 init_density 的初始化值。

  变更5: init_pos 同步修复

 新代码 BasicPlace.py:490-494 在 self.pos 创建后强制覆写：
 self.pos[0].data.copy_(torch.from_numpy(self.init_pos).to(self.pos[0].device))

---

## 14. GP Noise=0 Universal Optimization (2026-04-02)

目标：在保持固定 `update_mask` 行为与 `specpart_mode=gift_then_spectral` 的前提下，
将 **final placement** 的 `gp_noise_ratio` 置零，并自动执行：

1. B0 基线（cand_a 参数 + `gp_noise_ratio=0`）12 设计重跑  
2. 若不理想，执行高预算参数搜索（Round-1 + Round-2）  
3. 对选中候选做 12×6 seeds 稳定性实验（`cluster_random_seed=random_seed=seed`）  
4. 输出 HPWL 与 CV 统计，并生成实验报告

### 14.1 Isolation Policy

- 不改主线 runner：保留 `run_complete_flow_with_json.py` 原状  
- 新增隔离 runner：`run_complete_flow_with_json_gp0opt.py`  
- 仅在 final placement config 写入 `gp_noise_ratio`

### 14.2 New Scripts / Paths

- Runner copy:
  - `fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/run_complete_flow_with_json_gp0opt.py`
- Automation:
  - `fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/k_specpart_experiment/universal_search_gp0_20260402/run_gp0_universal_optimization.py`
- Experiment root:
  - `/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/k_specpart_experiment/universal_search_gp0_20260402`

### 14.3 Automation Outputs

- Candidate leaderboard:
  - `leaderboard.csv`, `leaderboard.json`
- Selected candidate:
  - `selected_candidate.json`
- Stability:
  - `stability_<candidate>/trial_results.csv|json`
  - `stability_<candidate>/design_stats.csv|json`
  - `stability_<candidate>/global_stability_stats.json`
- Report:
  - `REPORT_gp0_universal_optimization.md`

### 14.4 2026-04-02 Guarded Search Update

- Resume guard:
  - `run_gp0_universal_optimization.py` now inspects `4_final_input/final_placement.log`;
    if traceback/NaN markers exist, job status is recorded as `failed_existing` instead of `existing`.
  - This prevents failed runs with an `iter 0` HPWL line from being miscounted as valid.
- Conservative search band for `gp_noise_ratio=0`:
  - Round-1 candidates were shifted toward lower `density_weight`, lower `learning_rate`,
    and softer `gamma` to reduce `iter 0` numerical blow-up risk.
- No-complete diagnostics:
  - If no candidate finishes all 12 designs, the script now writes
    `no_complete_candidate_debug.json` and exits with a clear error.

### 14.5 2026-04-04 Universal Stability Search V2 Hard-Constraint Update

- Script:
  - `fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/run_universal_stability_search_v2.py`
- New feasibility rules (hard gate):
  - `mean_cv_pct < cv_baseline_mean_pct` (strict less-than)
  - `mean_hpwl_design_means <= ref_hpwl * (1 + hpwl_guardrail_pct / 100)`
- Selection rule:
  - Feasible-first deterministic ranking:
    1) lower `mean_hpwl_design_means`
    2) lower `mean_cv_pct`
    3) lower joint `score`
  - If no feasible candidate exists: fallback ranking by lower CV then HPWL.
- Adaptive fallback strategy:
  - Layered rounds with profiles `A/B/C` at expand step `0`.
  - If still infeasible, auto-expand runs additional layers using configured
    `adaptive_auto_expand_steps` (default `120,240`) with profile set `B/C`.
  - Adaptive path only changes
    `net_weight_anneal_iters`, `max_fanout`, `gamma`;
    keeps `learning_rate` and `density_weight` common/global.
- New outputs:
  - `search_round_summary.csv` (cross-round comparison table)
  - `feasibility_report.json` (constraint checks + chosen reason)
  - `stage3_adaptive/layer_XX_summaries.json`
