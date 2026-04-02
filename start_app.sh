#!/bin/bash
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=1
python3 app.py > flask_output.log 2>&1 &
echo $! > flask_pid.txt
