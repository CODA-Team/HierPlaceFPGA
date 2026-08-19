#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
SINGLE_RUN_SCRIPT="${SCRIPT_DIR}/run_three_models_single_graph_single_ub_cutoverlay.sh"

CASES=(
    denoise
    segmentation
    stereo_vision
    gsm_switch
)

UB_START="${UB_START:-1}"
UB_END="${UB_END:-20}"
NUM_SEEDS="${NUM_SEEDS:-5}"
SEED_START="${SEED_START:-100}"
SEED_STEP="${SEED_STEP:-200}"
SEED_WORKERS="${SEED_WORKERS:-5}"
CASE_WORKERS="${CASE_WORKERS:-4}"
JULIA_THREADS="${JULIA_THREADS:-1}"

BATCH_TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BATCH_ROOT="${BATCH_ROOT:-${PROJECT_ROOT}/experiments_revision/three_models_four_cases_ub01_20/${BATCH_TIMESTAMP}}"
LOG_ROOT="${BATCH_ROOT}/batch_logs"
STATUS_PART_ROOT="${BATCH_ROOT}/status_parts"
STATUS_CSV="${BATCH_ROOT}/batch_status.csv"
SUMMARY_CSV="${BATCH_ROOT}/four_cases_ub01_20_summary.csv"

if [[ ! "$UB_START" =~ ^[0-9]+$ ]] ||
   [[ ! "$UB_END" =~ ^[0-9]+$ ]] ||
   (( UB_START < 1 || UB_END > 49 || UB_START > UB_END )); then
    echo "ERROR: UB 范围必须满足 1 <= UB_START <= UB_END <= 49" >&2
    exit 2
fi
if [[ ! "$NUM_SEEDS" =~ ^[0-9]+$ ]] || (( NUM_SEEDS < 1 )); then
    echo "ERROR: NUM_SEEDS 必须是正整数" >&2
    exit 2
fi
if [[ ! "$SEED_WORKERS" =~ ^[0-9]+$ ]] || (( SEED_WORKERS < 1 )); then
    echo "ERROR: SEED_WORKERS 必须是正整数" >&2
    exit 2
fi
if [[ ! "$CASE_WORKERS" =~ ^[0-9]+$ ]] || (( CASE_WORKERS < 1 )); then
    echo "ERROR: CASE_WORKERS 必须是正整数" >&2
    exit 2
fi
if (( CASE_WORKERS > ${#CASES[@]} )); then
    CASE_WORKERS="${#CASES[@]}"
fi
if [[ ! -f "$SINGLE_RUN_SCRIPT" ]]; then
    echo "ERROR: 找不到单 case 运行脚本: $SINGLE_RUN_SCRIPT" >&2
    exit 1
fi

mkdir -p "$LOG_ROOT" "$STATUS_PART_ROOT"

echo "批量运行目录: $BATCH_ROOT"
echo "cases: ${CASES[*]}"
echo "UB: ${UB_START}..${UB_END}"
echo "模型和 Cut-Overlay seeds: NUM_SEEDS=$NUM_SEEDS, start=$SEED_START, step=$SEED_STEP"
echo "case_workers=$CASE_WORKERS, seed_workers=$SEED_WORKERS, julia_threads=$JULIA_THREADS"
echo "最多同时运行 $CASE_WORKERS 个 case；每个 case 内 UB 顺序执行"
echo "模型阶段理论最大并行任务数约为 $((CASE_WORKERS * 3 * SEED_WORKERS))"

run_one_case() {
    local benchmark="$1"
    local case_status="${STATUS_PART_ROOT}/${benchmark}.csv"
    local case_failed=0
    local ub ub2 run_root log_file result_csv

    : > "$case_status"
    for ((ub = UB_START; ub <= UB_END; ub++)); do
        printf -v ub2 '%02d' "$ub"
        run_root="${BATCH_ROOT}/${benchmark}/ub${ub2}"
        log_file="${LOG_ROOT}/${benchmark}_ub${ub2}.log"
        result_csv="${run_root}/cutoverlay/cutoverlay_three_models_summary.csv"

        if [[ -s "$result_csv" ]]; then
            echo "SKIP: $benchmark UB=$ub 已有成功结果"
            printf '%s\n' \
                "${benchmark},${ub},skipped_existing,${run_root},${log_file}" \
                >> "$case_status"
            continue
        fi

        echo
        echo "========== START: $benchmark UB=$ub =========="
        if RUN_ROOT="$run_root" \
           NUM_SEEDS="$NUM_SEEDS" \
           SEED_START="$SEED_START" \
           SEED_STEP="$SEED_STEP" \
           SEED_WORKERS="$SEED_WORKERS" \
           JULIA_THREADS="$JULIA_THREADS" \
           bash "$SINGLE_RUN_SCRIPT" "$benchmark" "$ub" \
           2>&1 | sed -u "s/^/[${benchmark} UB${ub2}] /" | tee "$log_file"; then
            if [[ -s "$result_csv" ]]; then
                echo "SUCCESS: $benchmark UB=$ub"
                printf '%s\n' \
                    "${benchmark},${ub},success,${run_root},${log_file}" \
                    >> "$case_status"
            else
                echo "ERROR: 命令返回成功，但缺少汇总 CSV: $result_csv" >&2
                printf '%s\n' \
                    "${benchmark},${ub},missing_summary,${run_root},${log_file}" \
                    >> "$case_status"
                case_failed=1
            fi
        else
            echo "ERROR: $benchmark UB=$ub 运行失败，继续下一个任务" >&2
            printf '%s\n' \
                "${benchmark},${ub},failed,${run_root},${log_file}" \
                >> "$case_status"
            case_failed=1
        fi
    done
    return "$case_failed"
}

PIDS=()
PID_CASES=()
WORKER_FAILED=0

wait_worker_group() {
    local index
    for index in "${!PIDS[@]}"; do
        if ! wait "${PIDS[$index]}"; then
            echo "WARNING: case ${PID_CASES[$index]} 中至少一个 UB 失败" >&2
            WORKER_FAILED=1
        fi
    done
    PIDS=()
    PID_CASES=()
}

for benchmark in "${CASES[@]}"; do
    run_one_case "$benchmark" &
    PIDS+=("$!")
    PID_CASES+=("$benchmark")
    if (( ${#PIDS[@]} >= CASE_WORKERS )); then
        wait_worker_group
    fi
done
if (( ${#PIDS[@]} > 0 )); then
    wait_worker_group
fi

printf '%s\n' \
    "benchmark,ub,status,run_root,log_file" \
    > "$STATUS_CSV"
for benchmark in "${CASES[@]}"; do
    case_status="${STATUS_PART_ROOT}/${benchmark}.csv"
    if [[ -s "$case_status" ]]; then
        cat "$case_status" >> "$STATUS_CSV"
    fi
done

SUCCEEDED="$(
    awk -F, 'NR > 1 && ($3 == "success" || $3 == "skipped_existing") {count++}
        END {print count + 0}' "$STATUS_CSV"
)"
FAILED="$(
    awk -F, 'NR > 1 && ($3 == "failed" || $3 == "missing_summary") {count++}
        END {print count + 0}' "$STATUS_CSV"
)"

printf '%s\n' \
    "benchmark,ub,cutoverlay_cutsize,best_seed,cutoverlay_mean_cutsize,valid_seed_count,total_seed_count,total_elapsed_sec,overlay_build_elapsed_sec,best_seed_elapsed_sec,final_part" \
    > "$SUMMARY_CSV"

for benchmark in "${CASES[@]}"; do
    for ((ub = UB_START; ub <= UB_END; ub++)); do
        printf -v ub2 '%02d' "$ub"
        result_csv="${BATCH_ROOT}/${benchmark}/ub${ub2}/cutoverlay/cutoverlay_three_models_summary.csv"
        if [[ -s "$result_csv" ]]; then
            tail -n 1 "$result_csv" >> "$SUMMARY_CSV"
        fi
    done
done

echo
echo "批量运行结束:"
echo "  成功或已存在: $SUCCEEDED"
echo "  失败: $FAILED"
echo "  状态表: $STATUS_CSV"
echo "  Cut-Overlay 汇总: $SUMMARY_CSV"

if (( FAILED > 0 || WORKER_FAILED > 0 )); then
    exit 1
fi
