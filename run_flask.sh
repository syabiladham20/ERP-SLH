#!/bin/bash
export FLASK_APP=app.py
export FLASK_ENV=development
python -m flask run --port 5000 > flask.log 2>&1 &
echo $! > flask.pid
