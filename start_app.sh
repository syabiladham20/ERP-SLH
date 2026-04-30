#!/bin/bash
source test-env/bin/activate
export FLASK_APP=run.py
export FLASK_ENV=development
export FLASK_RUN_PORT=5000
flask run &
echo $! > flask.pid
