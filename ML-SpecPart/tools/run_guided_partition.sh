#!/bin/bash
# End-to-end flow: HyperCutNet cut-prob -> TritonPart guided partitioning
#
# Usage:
#   ./run_guided_partition.sh [options] <hgr_file>
#
# Options:
#   -o, --openroad PATH    Path to openroad binary (default: ../TritonPart/build/openroad)
#   -c, --checkpoint PATH  HyperCutNet model checkpoint .pth (optional; if missing, uses dummy 0.5 probs)
#   -n, --num_parts N      Number of partitions (default: 2)
#   -b, --balance B        Balance constraint (default: 5)
#   -r, --repeats N        Number of runs (default: 1)
#   -w, --workdir DIR      Work directory (default: ./guided_run)
#   -e, --conda_env NAME   Conda env for step 2 (e.g. dgl_new)
#   --no_guide             Disable both coarsening and refinement guidance
#   --guide_coarsening 0/1 Explicitly control coarsening guidance (default: 1)
#   --guide_refinement 0/1 Explicitly control refinement guidance (default: 1)
#   --guide_cutoverlay 0/1 Explicitly control cut-overlay guidance (default: 1)
#
# Example:
#   ./run_guided_partition.sh ../TritonPart/test/sample.hgr
#   ./run_guided_partition.sh -c model.pth ../TritonPart/test/sample.hgr

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OPENROAD="${REPO_ROOT}/TritonPart/build/src/openroad"
CHECKPOINT=""
NUM_PARTS=2
BALANCE=5
REPEATS=1
WORKDIR="${REPO_ROOT}/outputs/guided_run"
NO_GUIDE=false
GUIDE_COARSENING=1
GUIDE_REFINEMENT=1
GUIDE_CUTOVERLAY=1
CONDA_ENV=""

while [[ $# -gt 0 ]]; do
  case $1 in
    -o|--openroad) OPENROAD="$2"; shift 2 ;;
    -c|--checkpoint) CHECKPOINT="$2"; shift 2 ;;
    -n|--num_parts) NUM_PARTS="$2"; shift 2 ;;
    -b|--balance) BALANCE="$2"; shift 2 ;;
    -r|--repeats) REPEATS="$2"; shift 2 ;;
    -w|--workdir) WORKDIR="$2"; shift 2 ;;
    -e|--conda_env) CONDA_ENV="$2"; shift 2 ;;
    --no_guide) NO_GUIDE=true; shift ;;
    --guide_coarsening) GUIDE_COARSENING="$2"; shift 2 ;;
    --guide_refinement) GUIDE_REFINEMENT="$2"; shift 2 ;;
    --guide_cutoverlay) GUIDE_CUTOVERLAY="$2"; shift 2 ;;
    -*) echo "Unknown option $1"; exit 1 ;;
    *) HGR_FILE="$1"; shift ;;
  esac
done

if [[ -z "$HGR_FILE" ]]; then
  echo "Usage: $0 [options] <hgr_file>"
  echo "  -o, --openroad PATH    Path to openroad (default: TritonPart/build/openroad)"
  echo "  -c, --checkpoint PATH  HyperCutNet checkpoint (optional)"
  echo "  -n, --num_parts N      Number of parts (default: 2)"
  echo "  -b, --balance B        Balance constraint (default: 5)"
  echo "  -r, --repeats N        Number of runs (default: 1)"
  echo "  -w, --workdir DIR      Work dir (default: tools/guided_run)"
  echo "  --no_guide             Disable both coarsening and refinement guidance"
  echo "  --guide_coarsening 0/1 Explicitly control coarsening guidance (default: 1)"
  echo "  --guide_refinement 0/1 Explicitly control refinement guidance (default: 1)"
  echo "  --guide_cutoverlay 0/1 Explicitly control cut-overlay guidance (default: 1)"
  exit 1
fi

HGR_ABS="$(cd "$(dirname "$HGR_FILE")" && pwd)/$(basename "$HGR_FILE")"
# Resolve checkpoint to absolute path (relative paths are from repo root)
if [[ -n "$CHECKPOINT" && "$CHECKPOINT" != /* ]]; then
  CHECKPOINT="$REPO_ROOT/$CHECKPOINT"
fi
mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "=== Step 1: Convert hgr -> HyperCutNet format ==="
HYPER_DIR="$WORKDIR/hypercutnet"
MARKER_FILE="$HYPER_DIR/.source_info"
HGR_MTIME="$(stat -c %Y "$HGR_ABS")"
HGR_SIZE="$(stat -c %s "$HGR_ABS")"

REUSE_CONVERSION=false
if [[ -f "$HYPER_DIR/nodes.txt" && -f "$HYPER_DIR/hedges.txt" && -f "$MARKER_FILE" ]]; then
  read -r SAVED_PATH SAVED_MTIME SAVED_SIZE < "$MARKER_FILE" || true
  if [[ "$SAVED_PATH" == "$HGR_ABS" && "$SAVED_MTIME" == "$HGR_MTIME" && "$SAVED_SIZE" == "$HGR_SIZE" ]]; then
    REUSE_CONVERSION=true
  fi
fi

if [[ "$REUSE_CONVERSION" == "true" ]]; then
  echo "  Reusing existing HyperCutNet graph files in $HYPER_DIR"
else
  python3 "$SCRIPT_DIR/hgr_to_hypercutnet.py" "$HGR_ABS" "$HYPER_DIR"
  echo "$HGR_ABS $HGR_MTIME $HGR_SIZE" > "$MARKER_FILE"
fi

echo "=== Step 2: Run HyperCutNet inference ==="
INF_ARGS=("$REPO_ROOT/HyperCutNet/src/inference.py" --graph_dir "$WORKDIR/hypercutnet" -o "$WORKDIR/cut_prob.txt" --ub_factor "$BALANCE")
[[ -n "$CHECKPOINT" ]] && INF_ARGS+=(--checkpoint "$CHECKPOINT")
if [[ -n "$CONDA_ENV" ]]; then
  PY_CMD=(conda run -n "$CONDA_ENV" python "${INF_ARGS[@]}")
else
  PY_CMD=(python3 "${INF_ARGS[@]}")
fi
INF_LOG="$WORKDIR/hypercutnet_inference.log"
: > "$INF_LOG"
if ! "${PY_CMD[@]}" >"$INF_LOG" 2>&1; then
  echo "  HyperCutNet inference FAILED (see $INF_LOG)."
  echo "  ---- Inference error (first 200 lines) ----"
  sed -n '1,200p' "$INF_LOG"
  echo "  ---- End of error log ----"
  exit 1
fi

echo "=== Step 3: Run TritonPart with cut probability guidance ==="
CUT_PROB_ABS="$(cd "$WORKDIR" && pwd)/cut_prob.txt"
# Derive guidance flags
if [[ "$NO_GUIDE" == "true" ]]; then
  GUIDE_COARSENING=0
  GUIDE_REFINEMENT=0
  GUIDE_CUTOVERLAY=0
fi

if [[ "$GUIDE_COARSENING" == "0" ]]; then
  COARSEN_FLAG="-guide_coarsening 0"
else
  COARSEN_FLAG="-guide_coarsening 1"
fi

if [[ "$GUIDE_REFINEMENT" == "0" ]]; then
  REFINE_FLAG="-guide_refinement 0"
else
  REFINE_FLAG="-guide_refinement 1"
fi

if [[ "$GUIDE_CUTOVERLAY" == "0" ]]; then
  CUTOVERLAY_FLAG="-guide_cutoverlay 0"
else
  CUTOVERLAY_FLAG="-guide_cutoverlay 1"
fi

if [[ "$GUIDE_COARSENING" == "0" && "$GUIDE_REFINEMENT" == "0" && "$GUIDE_CUTOVERLAY" == "0" ]]; then
  # No ML guidance at all; don't pass cut_prob_file
  CUT_LINE="$COARSEN_FLAG $REFINE_FLAG $CUTOVERLAY_FLAG"
else
  # Use cut_prob_file, but let each guidance flag control usage
  CUT_LINE="-cut_prob_file {$CUT_PROB_ABS} $COARSEN_FLAG $REFINE_FLAG $CUTOVERLAY_FLAG"
fi

if [[ ! -x "$OPENROAD" ]]; then
  echo "Error: openroad not found at $OPENROAD"
  echo "Build TritonPart first: cd TritonPart && mkdir -p build && cd build && cmake ../OpenROAD && make -j"
  exit 1
fi

# Prefer system libstdc++ first to avoid anaconda GLIBCXX version conflicts
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "=== Running TritonPart $REPEATS time(s) ==="
declare -a RUN_CUTS=()
SUMMARY_LOG="$WORKDIR/guided_run_summary.log"
> "$SUMMARY_LOG"

for ((run=0; run<REPEATS; run++)); do
  # Use a different random seed per run; base SEED can still be used
  # by the caller to influence the RNG sequence if desired.
  RUN_SEED=$RANDOM
  #RUN_SEED=$run
  TCL_SCRIPT="$WORKDIR/run_guided_run${run}.tcl"
  LOG_FILE="$WORKDIR/openroad_run${run}.log"

  cat > "$TCL_SCRIPT" << EOF
triton_part_hypergraph -hypergraph_file {$HGR_ABS} -num_parts $NUM_PARTS -balance_constraint $BALANCE -seed $RUN_SEED $CUT_LINE
exit
EOF

  echo "--- Run $run (seed=$RUN_SEED) ---"
  if ! "$OPENROAD" -no_init -exit "$TCL_SCRIPT" | tee "$LOG_FILE"; then
    echo "Error: OpenROAD failed for run $run (seed=$RUN_SEED)"
    exit 1
  fi

  # Extract the last reported cut cost from the log. Be robust to extra
  # punctuation/ANSI codes by stripping non-digits.
  CUT_COST=$(grep -F "Cutcost of partition" "$LOG_FILE" | tail -n 1 | sed -E 's/[^0-9]//g')
  if [[ -n "$CUT_COST" ]]; then
    echo "Run $run cutcost: $CUT_COST"
    RUN_CUTS[$run]="$CUT_COST"
  else
    echo "Run $run: could not parse cutcost from log."
    RUN_CUTS[$run]="NA"
  fi
done

# Summarize hyperparameters and results into a single log
{
  echo "=== Guided TritonPart summary ==="
  echo "Hypergraph      : $HGR_ABS"
  echo "Checkpoint      : ${CHECKPOINT:-<none>}"
  echo "OpenROAD        : $OPENROAD"
  echo "Num parts (k)   : $NUM_PARTS"
  echo "Balance (UB)    : $BALANCE"
  echo "Repeats         : $REPEATS"
  echo "Conda env       : ${CONDA_ENV:-<none>}"
  echo "Guide coarsening: $([[ \"$GUIDE_COARSENING\" == \"0\" ]] && echo \"false\" || echo \"true\")"
  echo "Guide refinement: $([[ \"$GUIDE_REFINEMENT\" == \"0\" ]] && echo \"false\" || echo \"true\")"
  echo "Guide cutoverlay: $([[ \"$GUIDE_CUTOVERLAY\" == \"0\" ]] && echo \"false\" || echo \"true\")"
  echo
  echo "Run,Seed,Cutcost"
  for ((run=0; run<REPEATS; run++)); do
    RUN_SEED="(random)"
    #RUN_SEED=$run
    echo "$run,$RUN_SEED,${RUN_CUTS[$run]}"
  done
} >> "$SUMMARY_LOG"

# Clean up temporary TCL scripts, keep logs for debugging/analysis
rm -f "$WORKDIR"/run_guided_run*.tcl
#rm -f "$WORKDIR"/openroad_run*.log

echo "=== Done. Solutions written to $WORKDIR/*.part.*; logs: $WORKDIR/openroad_run*.log; summary: $SUMMARY_LOG ==="
