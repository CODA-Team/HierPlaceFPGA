#!/bin/bash
# Script to safely stop tuner processes in container environment

echo "============================================================================"
echo "Stopping FPGA Clustering Pipeline Tuner"
echo "============================================================================"

# Find master process
MASTER_PID=$(ps aux | grep "tuner_train.py" | grep -v "worker" | grep -v grep | awk '{print $2}')
if [ -n "$MASTER_PID" ]; then
    echo "Found master process (PID: $MASTER_PID)"
    kill $MASTER_PID
    echo "  ✓ Master process stopped"
else
    echo "  ! No master process found"
fi

# Find and kill worker processes
WORKER_PIDS=$(ps aux | grep "tuner_train.py.*--worker" | grep -v grep | awk '{print $2}')
if [ -n "$WORKER_PIDS" ]; then
    echo "Found worker processes: $WORKER_PIDS"
    echo "$WORKER_PIDS" | xargs kill
    echo "  ✓ Worker processes stopped"
else
    echo "  ! No worker processes found"
fi

# Wait for graceful shutdown
sleep 2

# Check for remaining tuner processes
REMAINING=$(ps aux | grep "tuner_train.py" | grep -v grep | awk '{print $2}')
if [ -n "$REMAINING" ]; then
    echo "Force killing remaining tuner processes: $REMAINING"
    echo "$REMAINING" | xargs kill -9
fi

# Count running flow processes
FLOW_COUNT=$(ps aux | grep "run_complete_flow_with_json_area.py" | grep -v grep | wc -l)
if [ "$FLOW_COUNT" -gt 0 ]; then
    echo ""
    echo "⚠️  Warning: $FLOW_COUNT run_complete_flow processes still running"
    echo "   These will continue until completion or can be killed manually:"
    echo "   pkill -f 'run_complete_flow_with_json_area.py'"
fi

echo ""
echo "============================================================================"
echo "Tuner processes stopped"
echo "============================================================================"

