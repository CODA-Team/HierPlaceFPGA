#!/bin/bash
# FPGA Clustering Pipeline Parameter Tuning Script for Another Design (Enhanced Version)
# This script runs hyperparameter optimization for a different design in parallel
# Usage: ./run_tuner_another_design_enhanced.sh [DESIGN_NAME] [BENCHMARK_DIR]
# Example: ./run_tuner_another_design_enhanced.sh FPGA04 /work/fpga_clustering_pipline_gift/data/ispd2016/FPGA04

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
RUNTIME_RATIO=0       # Weight for runtime
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
    # FPGA03 -> 9093, FPGA04 -> 9094, FPGA05 -> 9095, etc.
    DESIGN_NUM=$(echo "$DESIGN_NAME" | grep -o '[0-9]\+' | head -1)
    if [ -n "$DESIGN_NUM" ]; then
        NAMESERVER_PORT=$((9090 + DESIGN_NUM))
    else
        # Fallback: use a random port in safe range
        NAMESERVER_PORT=$((9090 + RANDOM % 100))
    fi
fi

# Check if port is already in use and find next available port
check_port() {
    local port=$1
    if command -v netstat &> /dev/null; then
        netstat -tuln 2>/dev/null | grep -q ":${port} " && return 1
    elif command -v ss &> /dev/null; then
        ss -tuln 2>/dev/null | grep -q ":${port} " && return 1
    elif command -v lsof &> /dev/null; then
        lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1 && return 1
    fi
    return 0
}

# Find available port
ORIGINAL_PORT=$NAMESERVER_PORT
while ! check_port $NAMESERVER_PORT; do
    echo "Warning: Port $NAMESERVER_PORT is in use, trying next port..."
    NAMESERVER_PORT=$((NAMESERVER_PORT + 1))
    if [ $NAMESERVER_PORT -gt $((ORIGINAL_PORT + 100)) ]; then
        echo "Error: Could not find available port in range ${ORIGINAL_PORT}-$((ORIGINAL_PORT + 100))"
        exit 1
    fi
done

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
echo "Number of workers: $N_WORKERS"
echo "Number of iterations: $N_ITERATIONS"
echo "============================================================================"
echo ""

# Create log directory
mkdir -p "$LOG_DIR"

# Store PIDs for cleanup
declare -a WORKER_PIDS
MASTER_PID=""

# Cleanup function for signal handling
cleanup() {
    echo ""
    echo "============================================================================"
    echo "Caught signal, cleaning up processes..."
    echo "============================================================================"
    
    # Kill all workers
    if [ ${#WORKER_PIDS[@]} -gt 0 ]; then
        echo "Stopping ${#WORKER_PIDS[@]} worker processes..."
        for pid in "${WORKER_PIDS[@]}"; do
            kill $pid 2>/dev/null || true
        done
    fi
    
    # Kill master
    if [ -n "$MASTER_PID" ]; then
        echo "Stopping master process (PID: $MASTER_PID)..."
        kill $MASTER_PID 2>/dev/null || true
    fi
    
    # Wait for all processes to finish
    sleep 2
    
    # Force kill if still running
    for pid in $MASTER_PID "${WORKER_PIDS[@]}"; do
        if ps -p $pid > /dev/null 2>&1; then
            echo "Force killing PID: $pid"
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    echo "Cleanup complete"
    exit 130
}

# Set up signal trap
trap cleanup INT TERM

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

# Wait a bit for master to start and verify it's running
sleep 3
if ! ps -p $MASTER_PID > /dev/null 2>&1; then
    echo "Error: Master process failed to start or crashed immediately"
    exit 1
fi

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
    
    # Brief pause between worker starts
    sleep 0.5
done

echo ""
echo "============================================================================"
echo "All processes started. Monitoring ${DESIGN_NAME} tuning..."
echo "============================================================================"
echo "You can monitor progress by checking:"
echo "  - Log directory: $LOG_DIR"
echo "  - Master log: $LOG_DIR/results.json"
echo "  - Config log: $LOG_DIR/configs.json"
echo ""
echo "To stop all processes manually:"
echo "  kill $MASTER_PID ${WORKER_PIDS[@]}"
echo ""
echo "Or press Ctrl+C to gracefully stop all processes"
echo "============================================================================"

# Wait for master to complete
echo "Waiting for master process to complete..."
wait $MASTER_PID
MASTER_EXIT=$?

echo ""
echo "Master process completed with exit code: $MASTER_EXIT"
echo "Waiting for all worker processes to finish..."

# Wait for all workers to complete
for ((i=0; i<$N_WORKERS; i++)); do
    if ps -p ${WORKER_PIDS[$i]} > /dev/null 2>&1; then
        wait ${WORKER_PIDS[$i]} 2>/dev/null || true
        echo "  Worker $i completed"
    else
        echo "  Worker $i already terminated"
    fi
done

echo ""
echo "============================================================================"
echo "Tuning completed successfully!"
echo "============================================================================"
echo "Design: $DESIGN_NAME"
echo "Exit code: $MASTER_EXIT"
echo "Results saved to: $LOG_DIR"
echo "Best configurations: $LOG_DIR/best_cfgs/"
echo ""
echo "Summary files:"
echo "  - Results: $LOG_DIR/results.json"
echo "  - Configs: $LOG_DIR/configs.json"
echo "============================================================================"

exit $MASTER_EXIT

