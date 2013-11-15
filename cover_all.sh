#!/bin/bash
# Utility script to call the Python tool "coverage" for all test modules

# Interpreters to run the tests
TEST_PYTHONS=("python" "python3" "pypy")

# Modules to test
TEST_MODULES=("utilities" "ldapfilter" "threadpool" "pelix" "ipopo" \
              "http/basic" "shell/core" "configadmin")

# Interpreter to use to combine files, etc
DEFAULT_PYTHON="python"

# Python snippet to start coverage
COVERAGE="import coverage; coverage.main()"

# HTML report output directory
OUT_HTML=./htmlcov

# ------------------------------------------------------------------------------

echo "Preparing coverage configuration..."
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

echo "Erase..."
rm -fr $OUT_HTML
$DEFAULT_PYTHON -c "$COVERAGE" erase

for PYTHON in "${TEST_PYTHONS[@]}"
do
    # Test the interpreter
    $PYTHON --version >/dev/null 2>&1
    if [ $? -eq 0 ]
    then
        echo "Run... using $PYTHON"
        for i in ${TEST_MODULES[@]}
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
