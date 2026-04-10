#!/bin/bash
echo "Scanning migrations for ghost references..."
grep -rnw migrations/versions/ -e "erp\|slhop"
echo "If any files are listed above, delete them. Then run:"
echo "export FLASK_APP=app.py"
echo "flask db stamp head"
