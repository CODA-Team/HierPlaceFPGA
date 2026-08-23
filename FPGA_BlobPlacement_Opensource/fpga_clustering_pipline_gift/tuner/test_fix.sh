#!/bin/bash
# Quick test script to verify the path fix works
# This runs a minimal tuning session (1 iteration, 1 worker, 2 samples)

echo "============================================================================"
echo "Quick Test: Verifying Path Fix"
echo "============================================================================"

# Configuration
BENCHMARK_DIR="/work/fpga_clustering_pipline_gift/data/ispd2016/FPGA03"
DREAMPLACE_PATH="/work/fpga_clustering_pipline_gift/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA"
LOG_DIR="./logs_tuner_test_$(date +%Y%m%d_%H%M%S)"
RUN_ID="test_fix_$(date +%Y%m%d_%H%M%S)"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Test configuration:"
echo "  Benchmark: $BENCHMARK_DIR"
echo "  DREAMPlace: $DREAMPLACE_PATH"
echo "  Log dir: $LOG_DIR"
echo "  Iterations: 1"
echo "  Workers: 1"
echo "  Samples: 2"
echo ""

# Create log directory
mkdir -p "$LOG_DIR"

# Build run_args
RUN_ARGS=(
    "benchmark_dir=$BENCHMARK_DIR"
    "dreamplace_path=$DREAMPLACE_PATH"
    "base_ppa=FPGA03"
    "gpu=0"
)

echo "Starting test run..."
echo ""

# Start master process (in background)
python "$SCRIPT_DIR/tuner_train.py" \
    --multiobj false \
    --cfgSearchFile "$SCRIPT_DIR/configspace.json" \
    --n_iterations 1 \
    --n_workers 1 \
    --n_samples 2 \
    --min_points_in_model 2 \
    --hpwl_ratio 1.0 \
    --runtime_ratio 0.3 \
    --overflow_ratio 0.5 \
    --log_dir "$LOG_DIR" \
    --run_id "$RUN_ID" \
    --gpu_pool "-1" \
    --run_args "${RUN_ARGS[@]}" \
    &

MASTER_PID=$!
echo "Master process started (PID: $MASTER_PID)"
sleep 3

# Start 1 worker
python "$SCRIPT_DIR/tuner_train.py" \
    --worker \
    --worker_id 0 \
    --multiobj false \
    --cfgSearchFile "$SCRIPT_DIR/configspace.json" \
    --hpwl_ratio 1.0 \
    --runtime_ratio 0.3 \
    --overflow_ratio 0.5 \
    --log_dir "$LOG_DIR" \
    --run_id "$RUN_ID" \
    --gpu_pool "-1" \
    --run_args "${RUN_ARGS[@]}" \
    &

WORKER_PID=$!
echo "Worker process started (PID: $WORKER_PID)"
echo ""

echo "============================================================================"
echo "Monitoring test run..."
echo "============================================================================"
echo "Log directory: $LOG_DIR"
echo ""
echo "To monitor progress:"
echo "  tail -f $LOG_DIR/run-*/flow.log"
echo ""
echo "To check results:"
echo "  cat $LOG_DIR/results.json"
echo ""
echo "Press Ctrl+C to stop monitoring (processes will continue)"
echo "============================================================================"
echo ""

# Wait for master to complete
wait $MASTER_PID
EXIT_CODE=$?

echo ""
echo "============================================================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed successfully!"
    echo ""
    echo "Checking results..."
    
    # Check if results.json exists and has content
    if [ -f "$LOG_DIR/results.json" ]; then
        RESULT_COUNT=$(cat "$LOG_DIR/results.json" | grep -c "loss" || echo "0")
        echo "  Found $RESULT_COUNT result(s) in results.json"
        
        # Check for path errors
        PATH_ERRORS=$(grep -r "FileNotFoundError\|No such file.*dreamplace_config" "$LOG_DIR" 2>/dev/null | wc -l)
        if [ "$PATH_ERRORS" -eq 0 ]; then
            echo "  ✓ No path errors found!"
        else
            echo "  ✗ Found $PATH_ERRORS path error(s)"
        fi
        
        # Show first result
        echo ""
        echo "First result:"
        head -1 "$LOG_DIR/results.json" | python -m json.tool 2>/dev/null || head -1 "$LOG_DIR/results.json"
    else
        echo "  ! results.json not found"
    fi
else
    echo "✗ Test failed with exit code: $EXIT_CODE"
    echo ""
    echo "Check logs:"
    echo "  $LOG_DIR/run-*/flow.log"
fi
echo "============================================================================"



