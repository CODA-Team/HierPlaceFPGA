#!/bin/bash
# Script to safely stop the tuner processes

echo "Stopping tuner processes..."

# Find and kill master process
MASTER_PID=$(ps aux | grep "tuner_train.py" | grep -v "worker" | grep -v grep | awk '{print $2}')
if [ -n "$MASTER_PID" ]; then
    echo "Stopping master process (PID: $MASTER_PID)"
    kill $MASTER_PID
fi

# Find and kill worker processes
WORKER_PIDS=$(ps aux | grep "tuner_train.py.*--worker" | grep -v grep | awk '{print $2}')
if [ -n "$WORKER_PIDS" ]; then
    echo "Stopping worker processes: $WORKER_PIDS"
    echo "$WORKER_PIDS" | xargs kill
fi

# Wait a bit for graceful shutdown
sleep 3

# Force kill if still running
REMAINING=$(ps aux | grep "tuner_train.py" | grep -v grep | awk '{print $2}')
if [ -n "$REMAINING" ]; then
    echo "Force killing remaining processes: $REMAINING"
    echo "$REMAINING" | xargs kill -9
fi

# Note: run_complete_flow processes will finish naturally or can be killed separately
echo ""
echo "Tuner processes stopped."
echo "Note: run_complete_flow processes may still be running."
echo "To kill them: pkill -f 'run_complete_flow_with_json_area.py'"

