# SpecPart Cut-Overlay component

This directory contains the Julia source required by ML-SpecPart's three-model
Cut-Overlay flow. It is derived from the SpecPart implementation in the
TILOS-AI-Institute HypergraphPartitioning project; see `LICENSE` for the
upstream license and attribution.

## Install Julia dependencies

Julia 1.10 or newer is recommended.

```bash
julia --project=SpecPart -e 'using Pkg; Pkg.instantiate()'
```

## Configure OpenROAD

By default, the scripts use:

```text
<ML-SpecPart>/TritonPart/build/src/openroad
```

Override that location when necessary:

```bash
export SPECPART_OPENROAD_BIN=/path/to/openroad
```

Optional runtime variables are:

```bash
export SPECPART_READLINE_LIB=/path/to/libreadline.so
export SPECPART_OPENROAD_LIBRARY_PATH=/path/one:/path/two
export SPECPART_OPENROAD_LAUNCHER=/path/to/launcher
```

The launcher, when provided, is invoked as:

```text
launcher openroad_binary generated_script.tcl
```

## Entry point

The public ML-SpecPart shell wrappers call:

```text
run_cutoverlay_three_model_solutions_single_ub.jl
```

It expects exactly three completed model experiment directories. Each directory
must contain `ub_sweep_compare_with_inference_multiseed_best.csv` and its
corresponding guided-best `.part.2` file.
