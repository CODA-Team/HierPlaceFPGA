#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/tools/DREAMPlaceFPGA:${PYTHONPATH:-}"
export SPECPART_ROOT="${SPECPART_ROOT:-$ROOT/external/HypergraphPartitioning-main}"
export K_SPECPART_JL="${K_SPECPART_JL:-$SPECPART_ROOT/K_SpecPart/K_SpecPartWrapper.jl}"
export HMETIS_EXEC="${HMETIS_EXEC:-$ROOT/hmetis_api/hmetis_api/src/hmetis}"

OUT_DIR="${1:-$ROOT/smoke_public_release_case1_iter20}"
mkdir -p "$OUT_DIR"

python run_complete_flow_with_json.py \
  --convert_public_release \
  --benchmark_dir public_release \
  --convert_arch_dir Arch \
  --convert_case case_1 \
  --output_dir "$OUT_DIR" \
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
  --cluster_iteration 20 \
  --final_iteration 20 \
  --max_fanout 500 \
  --gpu 0 \
  --no_viz \
  --run_final_placement \
  --final_dreamplace_compat

echo "Smoke run finished: $OUT_DIR"
echo "Check generated final input: $OUT_DIR/4_final_input"
echo "DREAMPlace compatibility view, if final placement was run: $OUT_DIR/4_final_input_dreamplace_compat"
