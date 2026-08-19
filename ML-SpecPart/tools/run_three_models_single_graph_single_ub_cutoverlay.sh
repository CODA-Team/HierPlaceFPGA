#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
用法:
  bash tools/run_three_models_single_graph_single_ub_cutoverlay.sh <benchmark> <UB>

示例:
  bash tools/run_three_models_single_graph_single_ub_cutoverlay.sh sparcT1_core 5

可选环境变量:
  SEED_WORKERS=5       每个模型内部并行运行的 seed 数
  JULIA_THREADS=1      最终单图 Cut-Overlay 使用的 Julia 线程数
  NUM_SEEDS=5          Cut-Overlay 后 TritonPart 尝试的 seed 数
  RUN_ROOT=/path       指定本次输出目录；目录必须不存在或为空
  CHECKPOINT_TRITONPART=/path/to/model.pth
  CHECKPOINT_HMETIS=/path/to/model.pth
  CHECKPOINT_KAHYPAR=/path/to/model.pth
  PROJECT_ROOT=/path/to/ML-SpecPart
  SPECPART_ROOT=/path/to/SpecPart
  INFER_PYTHON=/path/to/python
  IBM_GRAPH_ROOT=/path/to/ibm/graphs
  TITAN_GRAPH_ROOT=/path/to/titan/graphs
EOF
}

if [[ $# -ne 2 ]]; then
    usage >&2
    exit 2
fi

BENCHMARK="$1"
UB="$2"

if [[ ! "$BENCHMARK" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "ERROR: benchmark 名称包含不允许的字符: $BENCHMARK" >&2
    exit 2
fi
if [[ ! "$UB" =~ ^[0-9]+$ ]] || (( UB < 1 || UB > 49 )); then
    echo "ERROR: UB 必须是 1 到 49 之间的整数: $UB" >&2
    exit 2
fi
printf -v UB_PADDED '%02d' "$UB"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
SPECPART_ROOT="${SPECPART_ROOT:-${PROJECT_ROOT}/SpecPart}"
BATCH_RUNNER="${BATCH_RUNNER:-${PROJECT_ROOT}/tools/run_batch_cases_from_testlists.py}"
INFERENCE_SCRIPT="${INFERENCE_SCRIPT:-${PROJECT_ROOT}/HyperCutNet/src/inference.py}"
INFER_PYTHON="${INFER_PYTHON:-python}"
JULIA_BIN="${JULIA_BIN:-julia}"
JULIA_SCRIPT="${SPECPART_ROOT}/run_cutoverlay_three_model_solutions_single_ub.jl"

IBM_HGR_DIR="${IBM_HGR_DIR:-${PROJECT_ROOT}/TritonPart/ISPD_benchmark}"
TITAN_HGR_DIR="${TITAN_HGR_DIR:-${PROJECT_ROOT}/TritonPart/titan23_benchmark}"
IBM_GRAPH_ROOT="${IBM_GRAPH_ROOT:-${PROJECT_ROOT}/datasets/hypercutnet/ibm}"
TITAN_GRAPH_ROOT="${TITAN_GRAPH_ROOT:-${PROJECT_ROOT}/datasets/hypercutnet/titan}"

CHECKPOINT_TRITONPART="${CHECKPOINT_TRITONPART:-${PROJECT_ROOT}/checkpoints/titan11_TritonPart_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth}"
CHECKPOINT_HMETIS="${CHECKPOINT_HMETIS:-${PROJECT_ROOT}/checkpoints/titan11_hMETIS_pin2net_gat_chunk30k_group_bs5_from_train_v2/best_model_graph_split.pth}"
CHECKPOINT_KAHYPAR="${CHECKPOINT_KAHYPAR:-${PROJECT_ROOT}/checkpoints/titan11_Kahyper_pin2net_gat_chunk30k_group_bs5_from_scratch_v1/best_model_graph_split.pth}"

SEED_WORKERS="${SEED_WORKERS:-5}"
NUM_SEEDS="${NUM_SEEDS:-5}"
SEED_START="${SEED_START:-100}"
SEED_STEP="${SEED_STEP:-200}"
JULIA_THREADS="${JULIA_THREADS:-1}"
PYTHON_BIN="${PYTHON_BIN:-python}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEFAULT_RUN_ROOT="${PROJECT_ROOT}/experiments_revision/three_models_single_graph_single_ub/${BENCHMARK}/ub${UB_PADDED}/${TIMESTAMP}"
RUN_ROOT="${RUN_ROOT:-$DEFAULT_RUN_ROOT}"

require_file() {
    if [[ ! -f "$1" ]]; then
        echo "ERROR: 找不到文件: $1" >&2
        exit 1
    fi
}

require_executable() {
    if [[ ! -x "$1" ]]; then
        echo "ERROR: 找不到可执行程序: $1" >&2
        exit 1
    fi
}

require_file "$BATCH_RUNNER"
require_file "$INFERENCE_SCRIPT"
require_file "$JULIA_SCRIPT"
require_file "$CHECKPOINT_TRITONPART"
require_file "$CHECKPOINT_HMETIS"
require_file "$CHECKPOINT_KAHYPAR"
require_executable "$INFER_PYTHON"
require_executable "$JULIA_BIN"

if [[ -d "$RUN_ROOT" ]] && [[ -n "$(find "$RUN_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "ERROR: 为避免覆盖已有结果，RUN_ROOT 必须不存在或为空: $RUN_ROOT" >&2
    exit 1
fi

mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/lists"
EMPTY_LIST="${RUN_ROOT}/lists/empty.txt"
IBM_LIST="$EMPTY_LIST"
TITAN_LIST="$EMPTY_LIST"
: > "$EMPTY_LIST"

if [[ "${BENCHMARK,,}" == ibm* ]]; then
    IBM_LIST="${RUN_ROOT}/lists/single_ibm.txt"
    printf '%s\n' "$BENCHMARK" > "$IBM_LIST"
    HGR_FILE="${IBM_HGR_DIR}/${BENCHMARK}.hgr"
else
    TITAN_LIST="${RUN_ROOT}/lists/single_titan.txt"
    printf '%s\n' "$BENCHMARK" > "$TITAN_LIST"
    HGR_NAME="$BENCHMARK"
    if [[ "$BENCHMARK" == "cholesky_bdtii" ]]; then
        HGR_NAME="cholesky_bdti"
    fi
    HGR_FILE="${TITAN_HGR_DIR}/${HGR_NAME}.hgr"
fi
require_file "$HGR_FILE"

OUT_TRITONPART="${RUN_ROOT}/inference_tritonpart"
OUT_HMETIS="${RUN_ROOT}/inference_hmetis"
OUT_KAHYPAR="${RUN_ROOT}/inference_kahypar"
OUT_CUTOVERLAY="${RUN_ROOT}/cutoverlay"

COMMON_ARGS=(
    "$BATCH_RUNNER"
    --ibm-list "$IBM_LIST"
    --titan-list "$TITAN_LIST"
    --ibm-hgr-dir "$IBM_HGR_DIR"
    --titan-hgr-dir "$TITAN_HGR_DIR"
    --ibm-graph-root "$IBM_GRAPH_ROOT"
    --titan-graph-root "$TITAN_GRAPH_ROOT"
    --inference-script "$INFERENCE_SCRIPT"
    --infer-python "$INFER_PYTHON"
    --use_pagerank
    --use_ubfactor
    --ub_isolate
    --ub-start "$UB"
    --ub-end "$UB"
    --num-parts 2
    --guide-coarsening 1
    --guide-refinement 0
    --guide-cutoverlay 1
    --num-seeds "$NUM_SEEDS"
    --seed-start "$SEED_START"
    --seed-step "$SEED_STEP"
    --seed-workers "$SEED_WORKERS"
    --case-workers 1
)

echo "本次运行目录: $RUN_ROOT"
echo "benchmark=$BENCHMARK UB=$UB"
echo "同时启动三个模型；每个模型 seed_workers=$SEED_WORKERS"

"$PYTHON_BIN" "${COMMON_ARGS[@]}" \
    --checkpoint "$CHECKPOINT_TRITONPART" \
    --out-root "$OUT_TRITONPART" \
    > "${RUN_ROOT}/logs/tritonpart.log" 2>&1 &
PID_TRITONPART=$!

"$PYTHON_BIN" "${COMMON_ARGS[@]}" \
    --checkpoint "$CHECKPOINT_HMETIS" \
    --out-root "$OUT_HMETIS" \
    > "${RUN_ROOT}/logs/hmetis.log" 2>&1 &
PID_HMETIS=$!

"$PYTHON_BIN" "${COMMON_ARGS[@]}" \
    --checkpoint "$CHECKPOINT_KAHYPAR" \
    --out-root "$OUT_KAHYPAR" \
    > "${RUN_ROOT}/logs/kahypar.log" 2>&1 &
PID_KAHYPAR=$!

echo "PIDs: TritonPart=$PID_TRITONPART hMETIS=$PID_HMETIS KaHyPar=$PID_KAHYPAR"

FAILED=0
if ! wait "$PID_TRITONPART"; then
    echo "ERROR: TritonPart 模型推理失败，查看 ${RUN_ROOT}/logs/tritonpart.log" >&2
    FAILED=1
fi
if ! wait "$PID_HMETIS"; then
    echo "ERROR: hMETIS 模型推理失败，查看 ${RUN_ROOT}/logs/hmetis.log" >&2
    FAILED=1
fi
if ! wait "$PID_KAHYPAR"; then
    echo "ERROR: KaHyPar 模型推理失败，查看 ${RUN_ROOT}/logs/kahypar.log" >&2
    FAILED=1
fi
if (( FAILED != 0 )); then
    exit 1
fi

EXP_TRITONPART="${OUT_TRITONPART}/ub_sweep_${BENCHMARK}"
EXP_HMETIS="${OUT_HMETIS}/ub_sweep_${BENCHMARK}"
EXP_KAHYPAR="${OUT_KAHYPAR}/ub_sweep_${BENCHMARK}"
BEST_CSV="ub_sweep_compare_with_inference_multiseed_best.csv"

for EXP_DIR in "$EXP_TRITONPART" "$EXP_HMETIS" "$EXP_KAHYPAR"; do
    if [[ ! -s "${EXP_DIR}/${BEST_CSV}" ]]; then
        echo "ERROR: 推理进程结束，但缺少有效结果: ${EXP_DIR}/${BEST_CSV}" >&2
        exit 1
    fi
done

echo "三个模型推理全部成功，现在对三个 guided-best solution 做 Cut-Overlay"
JULIA_NUM_THREADS="$JULIA_THREADS" "$JULIA_BIN" \
    --project="$SPECPART_ROOT" \
    "$JULIA_SCRIPT" \
    "benchmark=$BENCHMARK" \
    "hgr_file=$HGR_FILE" \
    "out_dir=$OUT_CUTOVERLAY" \
    "exp_dirs=${EXP_TRITONPART};${EXP_HMETIS};${EXP_KAHYPAR}" \
    "ub=$UB" \
    "base_seed=$SEED_START" \
    "num_seeds=$NUM_SEEDS" \
    2>&1 | tee "${RUN_ROOT}/logs/cutoverlay.log"

echo
echo "全部完成:"
echo "  运行根目录: $RUN_ROOT"
echo "  最终分区: ${OUT_CUTOVERLAY}/parts/cutoverlay_three_models_ub${UB_PADDED}.part.2"
echo "  汇总 CSV: ${OUT_CUTOVERLAY}/cutoverlay_three_models_summary.csv"
