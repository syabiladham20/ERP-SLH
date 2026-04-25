#!/bin/bash
kill $(pgrep -f "python3 run.py") 2>/dev/null || true
sleep 1
export PYTHONPATH=.
python3 run.py > app_output.log 2>&1 &
