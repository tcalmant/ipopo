#!/bin/bash
# Utility script to call the Python tool "coverage" for all test modules

# ------------------------------------------------------------------------------

echo "Preparing coverage configuration..."
OUT_HTML=./htmlcov
COVERAGE_RC=.coveragerc

cat > $COVERAGE_RC <<EOF
[run]
parallel = True
source = pelix

[report]
exclude_lines =
    pragma: no cover
    raise AssertionError
    raise NotImplementedError
    if 0:
    if __name__ == .__main__.:

[html]
directory = $OUT_HTML
EOF

cat $COVERAGE_RC

# ------------------------------------------------------------------------------

export PYTHONPATH=$(pwd)
PYTHONS=("python" "python3" "pypy")
DEFAULT_PYTHON="python3"

COVERAGE="import coverage; coverage.main()"

echo "Erase..."
rm -fr $OUT_HTML
$DEFAULT_PYTHON -c "$COVERAGE" erase

for PYTHON in "${PYTHONS[@]}"
do
    # Test the interpreter
    $PYTHON --version >/dev/null 2>&1
    if [ $? -eq 0 ]
    then
        echo "Run... using $PYTHON"
        files=("utilities" "ldapfilter" "pelix" "ipopo" "http/basic")
        for i in ${files[@]}
        do
            echo "Working on $i"
            $PYTHON -c "$COVERAGE" run tests/${i}_test.py || exit 1
        done
    else
        echo ">>> $PYTHON not found <<<"
    fi
done

rm $COVERAGE_RC

echo "Combine..."
$DEFAULT_PYTHON -c "$COVERAGE" combine

echo "HTML..."
$DEFAULT_PYTHON -c "$COVERAGE" html

echo "Done."
$DEFAULT_PYTHON -m webbrowser $OUT_HTML/index.html
