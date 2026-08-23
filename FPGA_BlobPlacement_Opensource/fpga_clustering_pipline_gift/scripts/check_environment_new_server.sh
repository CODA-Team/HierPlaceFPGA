#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/tools/DREAMPlaceFPGA:${PYTHONPATH:-}"
export SPECPART_ROOT="${SPECPART_ROOT:-$ROOT/external/HypergraphPartitioning-main}"
export K_SPECPART_JL="${K_SPECPART_JL:-$SPECPART_ROOT/K_SpecPart/K_SpecPartWrapper.jl}"
export HMETIS_EXEC="${HMETIS_EXEC:-$ROOT/hmetis_api/hmetis_api/src/hmetis}"
SMOKE_DIR="$ROOT/_smoke_env_check"
rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR"

echo "[1/7] Paths"
echo "  ROOT=$ROOT"
echo "  SPECPART_ROOT=$SPECPART_ROOT"
echo "  K_SPECPART_JL=$K_SPECPART_JL"
echo "  HMETIS_EXEC=$HMETIS_EXEC"
test -f "$K_SPECPART_JL"
test -x "$HMETIS_EXEC"

echo "[2/7] Python syntax check"
python -m py_compile \
  run_complete_flow_with_json.py \
  convert_public_release_benchmark.py \
  cluster_placement_integration.py \
  fpga_clustering_pipeline_gift.py \
  main_pipeline_with_viz.py \
  gift_specpart_complete.py \
  net_reweighting_integration.py \
  cluster_conductance_analysis.py \
  adaptive_params.py \
  visualization_clustering.py

echo "[3/7] Python package imports"
python - <<'PY'
import importlib
mods = [
    "numpy", "scipy", "matplotlib", "sknetwork", "torch", "gurobipy",
]
for mod in mods:
    importlib.import_module(mod)
    print("  OK", mod)
PY

echo "[4/7] PyTorch / DREAMPlaceFPGA ABI info and native imports"
python - <<'PY'
import importlib
import torch
print("  torch=", torch.__version__)
print("  torch_cuda=", torch.version.cuda)
print("  torch_cxx11_abi=", torch._C._GLIBCXX_USE_CXX11_ABI)
mods = [
    "dreamplacefpga.ops.place_io.place_io",
    "dreamplacefpga.ops.hpwl.hpwl",
    "dreamplacefpga.ops.demandMap.demandMap",
    "dreamplacefpga.ops.pin_pos.pin_pos",
    "dreamplacefpga.ops.move_boundary.move_boundary",
]
for mod in mods:
    importlib.import_module(mod)
    print("  OK", mod)
PY

echo "[5/7] hMETIS binary smoke"
cat > "$SMOKE_DIR/tiny.hgr" <<'EOF'
1 2
1 2
EOF
"$HMETIS_EXEC" "$SMOKE_DIR/tiny.hgr" 2 5 1 1 1 0 1 0 0 >/dev/null
test -s "$SMOKE_DIR/tiny.hgr.part.2"
echo "  OK hMETIS generated $SMOKE_DIR/tiny.hgr.part.2"

echo "[6/7] Julia packages / K_SpecPart wrapper smoke"
cat > "$SMOKE_DIR/kspecpart_tiny.hgr" <<'EOF'
1 2
1 2
EOF
julia --startup-file=no "$K_SPECPART_JL"   --hgr "$SMOKE_DIR/kspecpart_tiny.hgr"   --output "$SMOKE_DIR/kspecpart_tiny.json"   --num_parts 2   --best_solns 1 >/dev/null
test -s "$SMOKE_DIR/kspecpart_tiny.json"
echo "  OK K_SpecPartWrapper generated $SMOKE_DIR/kspecpart_tiny.json"

echo "[7/7] public_release conversion smoke"
python convert_public_release_benchmark.py \
  --public_release_dir public_release \
  --arch_dir Arch \
  --case case_1 \
  --output_dir "$SMOKE_DIR/converted_case_1"
test -f "$SMOKE_DIR/converted_case_1/design.aux"
test -f "$SMOKE_DIR/converted_case_1/design.metadata.json"
echo "  OK converted benchmark at $SMOKE_DIR/converted_case_1"

echo "Environment smoke check PASSED"
