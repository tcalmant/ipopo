#!/bin/bash
# Utility script to call the Python tool "coverage" for a specific test module

export PYTHONPATH=$(pwd)

echo "Erase..."
coverage erase
rm -fr htmldoc 2>/dev/null

echo "Run..."
coverage run --source pelix tests/$1_test.py || exit 1

echo "HTML..."
coverage html

echo "Done."
python -m webbrowser ./htmlcov/index.html

