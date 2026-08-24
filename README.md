# HierPlaceFPGA

HierPlaceFPGA is an open-source research framework for hierarchical FPGA
placement and machine-learning-guided hypergraph partitioning. The repository
brings together two complementary components: an FPGA clustering and placement
pipeline, and ML-SpecPart for learned partition guidance and Cut-Overlay
refinement.

## Overview

The repository contains two complementary research components for FPGA design:
a hierarchical clustering and analytical placement flow, and an ML-guided
hypergraph-partitioning flow. Each component provides its own environment
setup, usage instructions, and validation workflow, and can be installed and
used independently.

## Key features

- Hierarchical FPGA clustering and analytical placement.
- GNN-based prediction for hypergraph partition guidance.
- Integration with TritonPart/OpenROAD for guided partitioning.
- Julia-based Cut-Overlay for combining solutions from multiple models.
- Benchmark conversion, environment validation, smoke tests, and batch
  experiment utilities.

## Repository structure

| Component | Description | Documentation |
| --- | --- | --- |
| [`FPGA_BlobPlacement_Opensource/`](FPGA_BlobPlacement_Opensource/) | Hierarchical FPGA clustering, net reweighting, and placement pipeline | [Packaged contents](FPGA_BlobPlacement_Opensource/PACKAGED_CONTENTS.md) |
| [`ML-SpecPart/`](ML-SpecPart/) | ML-guided hypergraph partitioning and multi-model Cut-Overlay | [ML-SpecPart user guide](ML-SpecPart/README.md) |

```text
HierPlaceFPGA/
├── FPGA_BlobPlacement_Opensource/  # FPGA clustering and placement flow
├── ML-SpecPart/                    # ML-guided partitioning flow
├── LICENSE                         # Repository license
└── README.md                       # Project overview and navigation
```

## Components

### FPGA Blob Placement

The FPGA Blob Placement component implements a hierarchical placement flow. It
clusters connected cells, performs cluster-level placement, reweights nets,
generates the final placement input, and optionally invokes DREAMPlaceFPGA for
the final analytical placement stage.

Its main workflow is organized into five phases:

1. Louvain, GiFt, and SpecPart-based clustering.
2. Cluster-level analytical placement.
3. Inter- and intra-cluster net reweighting.
4. Generation of the final placement input.
5. Optional final placement with DREAMPlaceFPGA.

Documentation:

- [Project structure and pipeline](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/PROJECT_STRUCTURE.md)
- [Environment setup](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/ENVIRONMENT_SETUP.md)
- [Validation summary](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/VALIDATION_SUMMARY.md)
- [New placer migration guide](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/MIGRATION_NEW_PLACER.md)
- [New-server migration runbook](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/MIGRATION_RUNBOOK_NEW_SERVER.md)

The principal entry point is:

```text
FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/run_complete_flow_with_json.py
```

### ML-SpecPart

ML-SpecPart provides an end-to-end learned hypergraph-partitioning flow built
from three subcomponents:

- **HyperCutNet** supplies GNN training and inference.
- **TritonPart** performs ML-guided hypergraph partitioning through OpenROAD.
- **SpecPart** combines candidate partitions using Julia Cut-Overlay.

Documentation:

- [ML-SpecPart installation and usage](ML-SpecPart/README.md)
- [HyperCutNet documentation](ML-SpecPart/HyperCutNet/README.md)
- [TritonPart documentation](ML-SpecPart/TritonPart/README.md)
- [SpecPart documentation](ML-SpecPart/SpecPart/README.md)

## Getting started

Clone the repository and select the component required for your experiment:

```bash
git clone https://github.com/CODA-Team/HierPlaceFPGA.git
cd HierPlaceFPGA
```

The two components use different software stacks and should be configured
separately:

- For FPGA clustering and placement, follow the
  [FPGA Blob Placement environment guide](FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift/ENVIRONMENT_SETUP.md).
- For learned hypergraph partitioning, follow the
  [ML-SpecPart installation guide](ML-SpecPart/README.md#installation).

Do not assume that one component's Python, Julia, native-library, or solver
environment can be reused by the other. Run the corresponding environment
check before starting a full experiment.

## Verification

For FPGA Blob Placement, the packaged environment and short-flow checks are:

```bash
cd FPGA_BlobPlacement_Opensource/fpga_clustering_pipline_gift
bash scripts/check_environment_new_server.sh
bash scripts/run_smoke_case1_iter20.sh /tmp/fpga_blobplacement_smoke
```

For ML-SpecPart, run the preflight check after installing its dependencies:

```bash
cd ML-SpecPart
INFER_PYTHON="$(command -v python)" \
JULIA_BIN="$(command -v julia)" \
bash tools/preflight_check.sh
```

See the component documentation for complete commands, input preparation,
configuration parameters, and output layouts.

## Inputs and outputs

| Component | Typical inputs | Typical outputs |
| --- | --- | --- |
| FPGA Blob Placement | FPGA Bookshelf designs, architecture files, and JSON parameters | Clustering results, placement inputs, placement logs, and final placement results |
| ML-SpecPart | Hypergraphs, HyperCutNet graph data, model checkpoints, and UB settings | Guided partitions, Cut-Overlay partitions, logs, and CSV summaries |

Generated builds, datasets, caches, and experiment outputs are not intended to
be committed to the source tree unless explicitly required for reproduction.

## Citation

If you use HierPlaceFPGA or one of its components in academic work, please cite
the corresponding publication. Citation metadata will be added here when it is
available.

## License

HierPlaceFPGA is distributed under the [BSD 3-Clause License](LICENSE).
Third-party projects and bundled subcomponents may include their own license
terms; consult the license files in the corresponding directories before use or
redistribution.

## Acknowledgements

This repository builds on third-party tools and libraries including OpenROAD,
DREAMPlaceFPGA, DGL, PyTorch, Julia, and hMETIS. We thank their developers and
contributors.
