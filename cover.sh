#!/bin/bash
# Utility script to call the Python tool "coverage" for a specific test module

export PYTHONPATH=$(pwd)
PYTHONS=("python" "python3")
DEFAULT_PYTHON="python3"

COVERAGE="import coverage; coverage.main()"

echo "Erase..."
rm -fr htmlcov
$DEFAULT_PYTHON -c "$COVERAGE" erase

for PYTHON in "${PYTHONS[@]}"
do
    echo "Run... using $PYTHON"
    $PYTHON -c "$COVERAGE" run --source pelix --parallel-mode tests/$1_test.py || exit 1
done

echo "Combine..."
$DEFAULT_PYTHON -c "$COVERAGE" combine

echo "HTML..."
$DEFAULT_PYTHON -c "$COVERAGE" html

echo "Done."
$DEFAULT_PYTHON -m webbrowser ./htmlcov/index.html

