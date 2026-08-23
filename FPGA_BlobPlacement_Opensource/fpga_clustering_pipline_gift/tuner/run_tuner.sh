#!/bin/bash
# FPGA Clustering Pipeline Parameter Tuning Script
# This script runs hyperparameter optimization for the fpga_clustering_pipline_gift project

# ============================================================================
# Configuration
# ============================================================================

# Benchmark configuration
BENCHMARK_DIR="/work/fpga_clustering_pipline_gift/data/ispd2016/FPGA03"
DREAMPLACE_PATH="/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA"
AUX_FILE=""  # Leave empty to auto-detect

# Tuning configuration
N_ITERATIONS=50        # Number of BOHB iterations
N_WORKERS=4           # Number of parallel workers
N_SAMPLES=32          # Number of samples per iteration
MIN_POINTS=16         # Minimum points before building KDE model

# Multi-objective optimization (set to true for Pareto front, false for single objective)
MULTIOBJ=false
NUM_PARETO=5          # Number of Pareto points (only for multi-objective)

# Cost ratios (only for single objective)
HPWL_RATIO=1.0        # Weight for HPWL
RUNTIME_RATIO=0.3     # Weight for runtime
OVERFLOW_RATIO=0.5    # Weight for overflow

# GPU configuration
GPU_POOL="-1"         # GPU pool: "-1" for all GPUs, or "0,1,2" for specific GPUs

# Output configuration
LOG_DIR="./logs_tuner_$(date +%Y%m%d_%H%M%S)"
RUN_ID="tuning_$(date +%Y%m%d_%H%M%S)"

# PPA baseline (for normalization) - update with your baseline results
BASE_PPA="FPGA03"     # Or path to JSON file with baseline metrics

# Optional: reuse best parameters from previous run
REUSE_PARAMS=""       # Leave empty or set to "FPGA03" or path to JSON

# Configuration space file
CFG_SEARCH_FILE="./tuner/configspace.json"

# ============================================================================
# Script Start
# ============================================================================

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "============================================================================"
echo "FPGA Clustering Pipeline Hyperparameter Tuning"
echo "============================================================================"
echo "Project directory: $PROJECT_DIR"
echo "Log directory: $LOG_DIR"
echo "Benchmark: $BENCHMARK_DIR"
echo "DREAMPlace path: $DREAMPLACE_PATH"
echo "============================================================================"
echo ""

# Create log directory
mkdir -p "$LOG_DIR"

# Build run_args
RUN_ARGS=(
    "benchmark_dir=$BENCHMARK_DIR"
    "dreamplace_path=$DREAMPLACE_PATH"
    "base_ppa=$BASE_PPA"
    "gpu=0"
)

if [ -n "$AUX_FILE" ]; then
    RUN_ARGS+=("aux=$AUX_FILE")
fi

if [ -n "$REUSE_PARAMS" ]; then
    RUN_ARGS+=("reuse_params=$REUSE_PARAMS")
fi

# Start master process
echo "Starting master process..."
python "$SCRIPT_DIR/tuner_train.py" \
    --multiobj "$MULTIOBJ" \
    --cfgSearchFile "$CFG_SEARCH_FILE" \
    --n_iterations "$N_ITERATIONS" \
    --n_workers "$N_WORKERS" \
    --n_samples "$N_SAMPLES" \
    --min_points_in_model "$MIN_POINTS" \
    --hpwl_ratio "$HPWL_RATIO" \
    --runtime_ratio "$RUNTIME_RATIO" \
    --overflow_ratio "$OVERFLOW_RATIO" \
    --num_pareto "$NUM_PARETO" \
    --log_dir "$LOG_DIR" \
    --run_id "$RUN_ID" \
    --gpu_pool "$GPU_POOL" \
    --run_args "${RUN_ARGS[@]}" \
    &

MASTER_PID=$!
echo "Master process started with PID: $MASTER_PID"

# Wait a bit for master to start
sleep 3

# Start worker processes
echo "Starting $N_WORKERS worker processes..."
for ((i=0; i<$N_WORKERS; i++)); do
    python "$SCRIPT_DIR/tuner_train.py" \
        --worker \
        --worker_id "$i" \
        --multiobj "$MULTIOBJ" \
        --cfgSearchFile "$CFG_SEARCH_FILE" \
        --hpwl_ratio "$HPWL_RATIO" \
        --runtime_ratio "$RUNTIME_RATIO" \
        --overflow_ratio "$OVERFLOW_RATIO" \
        --log_dir "$LOG_DIR" \
        --run_id "$RUN_ID" \
        --gpu_pool "$GPU_POOL" \
        --run_args "${RUN_ARGS[@]}" \
        &
    
    WORKER_PIDS[$i]=$!
    echo "  Worker $i started with PID: ${WORKER_PIDS[$i]}"
done

echo ""
echo "============================================================================"
echo "All processes started. Waiting for completion..."
echo "============================================================================"
echo "You can monitor progress by checking:"
echo "  - Log directory: $LOG_DIR"
echo "  - Master log: $LOG_DIR/results.json"
echo ""
echo "To stop all processes:"
echo "  kill $MASTER_PID ${WORKER_PIDS[@]}"
echo "============================================================================"

# Wait for master to complete
wait $MASTER_PID
EXIT_CODE=$?

echo ""
echo "============================================================================"
echo "Tuning completed with exit code: $EXIT_CODE"
echo "============================================================================"
echo "Results saved to: $LOG_DIR"
echo "Best configurations: $LOG_DIR/best_cfgs"
echo "============================================================================"

exit $EXIT_CODE
