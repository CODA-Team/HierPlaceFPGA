#!/usr/bin/env bash
# Verify that the software needed by the public ML-SpecPart flow is available.
# This check does not execute an experiment or modify input data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
PYTHON_BIN="${INFER_PYTHON:-python}"
JULIA_BIN="${JULIA_BIN:-julia}"
OPENROAD_BIN="${SPECPART_OPENROAD_BIN:-${PROJECT_ROOT}/TritonPart/build/src/openroad}"

failed=0

pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; failed=1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
require_file() {
    if [[ -f "$1" ]]; then pass "$1"; else fail "missing file: $1"; fi
}

echo "ML-SpecPart preflight"
echo "project root: ${PROJECT_ROOT}"

require_file "${PROJECT_ROOT}/HyperCutNet/src/inference.py"
require_file "${PROJECT_ROOT}/SpecPart/Project.toml"
require_file "${PROJECT_ROOT}/SpecPart/run_cutoverlay_three_model_solutions_single_ub.jl"
require_file "${PROJECT_ROOT}/tools/run_three_models_single_graph_single_ub_cutoverlay.sh"
require_file "${PROJECT_ROOT}/checkpoints/titan11_TritonPart_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth"
require_file "${PROJECT_ROOT}/checkpoints/titan11_hMETIS_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth"
require_file "${PROJECT_ROOT}/checkpoints/titan11_Kahyper_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth"

if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if "$PYTHON_BIN" -c 'import torch, dgl, scipy, networkx, sklearn; print("Python dependencies OK; torch=" + torch.__version__ + ", dgl=" + dgl.__version__ + ", cuda=" + str(torch.cuda.is_available()))'; then
        pass "Python dependencies"
    else
        fail "Python dependencies are incomplete; create HyperCutNet/environment-cpu.yml first"
    fi
else
    fail "Python executable not found: ${PYTHON_BIN}"
fi

if command -v "$JULIA_BIN" >/dev/null 2>&1; then
    if "$JULIA_BIN" --project="${PROJECT_ROOT}/SpecPart" -e 'using CSV, DataFrames, Graphs, JuMP, Laplacians; println("Julia dependencies OK")'; then
        pass "Julia dependencies"
    else
        fail "Julia dependencies are incomplete; run: julia --project=SpecPart -e \"using Pkg; Pkg.instantiate()\""
    fi
else
    fail "Julia executable not found: ${JULIA_BIN}"
fi

if [[ -x "$OPENROAD_BIN" ]]; then
    if "$OPENROAD_BIN" -help >/dev/null 2>&1; then
        pass "OpenROAD executable: ${OPENROAD_BIN}"
    else
        fail "OpenROAD exists but cannot start: ${OPENROAD_BIN}"
    fi
else
    fail "OpenROAD executable not found: ${OPENROAD_BIN}"
fi

if [[ ! -d "${PROJECT_ROOT}/datasets/hypercutnet/ibm" || ! -d "${PROJECT_ROOT}/datasets/hypercutnet/titan" ]]; then
    warn "inference graph directories are absent. Set IBM_GRAPH_ROOT and TITAN_GRAPH_ROOT before the three-model flow."
else
    pass "inference graph directories"
fi

if (( failed != 0 )); then
    echo "Preflight failed." >&2
    exit 1
fi

echo "Preflight passed. You can run a single case after providing graph data."
