#!/bin/bash
# Utility script to call the Python tool "coverage" for all test modules

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
    files=("utilities" "ldapfilter" "pelix" "ipopo" "http/basic")
    for i in ${files[@]}
    do
        echo "Working on $i"
        $PYTHON -c "$COVERAGE" run --source pelix --parallel-mode tests/${i}_test.py || exit 1
    done
done

echo "Combine..."
$DEFAULT_PYTHON -c "$COVERAGE" combine

echo "HTML..."
$DEFAULT_PYTHON -c "$COVERAGE" html

echo "Done."
$DEFAULT_PYTHON -m webbrowser ./htmlcov/index.html
