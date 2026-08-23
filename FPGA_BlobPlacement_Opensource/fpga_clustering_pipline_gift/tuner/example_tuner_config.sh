#!/bin/bash
# Quick start example for tuning fpga_clustering_pipline_gift
# This is a minimal configuration for testing the tuner

# ============================================================================
# EDIT THESE PATHS
# ============================================================================
BENCHMARK_DIR="/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/data/ispd2016/FPGA03"
DREAMPLACE_PATH="/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA"

# ============================================================================
# Quick test configuration (fewer iterations)
# ============================================================================
N_ITERATIONS=5         # Small number for testing
N_WORKERS=2           # Fewer workers for testing
N_SAMPLES=8           # Fewer samples

LOG_DIR="./logs_tuner_test"
RUN_ID="test_run"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Starting quick tuning test..."
echo "This will run $N_ITERATIONS iterations with $N_WORKERS workers"
echo "Results will be saved to: $LOG_DIR"

python "$SCRIPT_DIR/tuner_train.py" \
    --n_iterations "$N_ITERATIONS" \
    --n_workers "$N_WORKERS" \
    --n_samples "$N_SAMPLES" \
    --min_points_in_model 4 \
    --log_dir "$LOG_DIR" \
    --run_id "$RUN_ID" \
    --hpwl_ratio 1.0 \
    --runtime_ratio 0.3 \
    --overflow_ratio 0.5 \
    --run_args \
        benchmark_dir="$BENCHMARK_DIR" \
        dreamplace_path="$DREAMPLACE_PATH" \
        base_ppa=FPGA03 \
        gpu=0 \
    &

MASTER_PID=$!
sleep 3

for ((i=0; i<$N_WORKERS; i++)); do
    python "$SCRIPT_DIR/tuner_train.py" \
        --worker \
        --worker_id "$i" \
        --log_dir "$LOG_DIR" \
        --run_id "$RUN_ID" \
        --run_args \
            benchmark_dir="$BENCHMARK_DIR" \
            dreamplace_path="$DREAMPLACE_PATH" \
            base_ppa=FPGA03 \
            gpu=0 \
        &
done

wait $MASTER_PID
echo "Tuning test completed! Check results in: $LOG_DIR"

