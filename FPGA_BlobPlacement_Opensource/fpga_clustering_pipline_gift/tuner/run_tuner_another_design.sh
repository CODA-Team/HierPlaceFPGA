#!/bin/bash
# FPGA Clustering Pipeline Parameter Tuning Script for Another Design
# This script runs hyperparameter optimization for a different design in parallel
# Usage: ./run_tuner_another_design.sh [DESIGN_NAME] [BENCHMARK_DIR]
# Example: ./run_tuner_another_design.sh FPGA04 /work/fpga_clustering_pipline_gift/data/ispd2016/FPGA04

# ============================================================================
# Configuration
# ============================================================================

# Get design name from command line or use default
DESIGN_NAME="${1:-FPGA04}"
BENCHMARK_DIR="${2:-/work/fpga_clustering_pipline_gift/data/ispd2016/${DESIGN_NAME}}"

# Check if benchmark directory exists
if [ ! -d "$BENCHMARK_DIR" ]; then
    echo "Error: Benchmark directory not found: $BENCHMARK_DIR"
    echo "Usage: $0 [DESIGN_NAME] [BENCHMARK_DIR]"
    echo "Example: $0 FPGA04 /work/fpga_clustering_pipline_gift/data/ispd2016/FPGA04"
    exit 1
fi

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
RUNTIME_RATIO=0     # Weight for runtime
OVERFLOW_RATIO=0.1    # Weight for overflow

# GPU configuration
GPU_POOL="-1"         # GPU pool: "-1" for all GPUs, or "0,1,2" for specific GPUs

# Output configuration - Use design name in log directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="./logs_tuner_${DESIGN_NAME}_${TIMESTAMP}"
RUN_ID="tuning_${DESIGN_NAME}_${TIMESTAMP}"

# PPA baseline (for normalization) - update with your baseline results
BASE_PPA="${DESIGN_NAME}"     # Or path to JSON file with baseline metrics

# Optional: reuse best parameters from previous run
REUSE_PARAMS=""       # Leave empty or set to design name or path to JSON

# Configuration space file
CFG_SEARCH_FILE="./tuner/configspace.json"

# Nameserver port - Use different port for each design to avoid conflicts
# Default HPBandSter uses port 9090, we'll use a different port based on design
# You can also manually specify: NAMESERVER_PORT=9091
if [ -z "$NAMESERVER_PORT" ]; then
    # Auto-select port based on design name hash (simple method)
    # FPGA03 -> 9090, FPGA04 -> 9091, FPGA05 -> 9092, etc.
    DESIGN_NUM=$(echo "$DESIGN_NAME" | grep -o '[0-9]\+' | head -1)
    if [ -n "$DESIGN_NUM" ]; then
        NAMESERVER_PORT=$((9090 + 10#$DESIGN_NUM))
    else
        # Fallback: use a random port in safe range
        NAMESERVER_PORT=$((9090 + RANDOM % 100))
    fi
fi

# ============================================================================
# Script Start
# ============================================================================

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "============================================================================"
echo "FPGA Clustering Pipeline Hyperparameter Tuning - ${DESIGN_NAME}"
echo "============================================================================"
echo "Project directory: $PROJECT_DIR"
echo "Log directory: $LOG_DIR"
echo "Benchmark: $BENCHMARK_DIR"
echo "DREAMPlace path: $DREAMPLACE_PATH"
echo "Design name: $DESIGN_NAME"
echo "Run ID: $RUN_ID"
echo "Nameserver port: $NAMESERVER_PORT"
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
    --nameserver_port "$NAMESERVER_PORT" \
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
        --nameserver_port "$NAMESERVER_PORT" \
        --gpu_pool "$GPU_POOL" \
        --run_args "${RUN_ARGS[@]}" \
        &
    
    WORKER_PIDS[$i]=$!
    echo "  Worker $i started with PID: ${WORKER_PIDS[$i]}"
done

echo ""
echo "============================================================================"
echo "All processes started. Monitoring ${DESIGN_NAME} tuning..."
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

