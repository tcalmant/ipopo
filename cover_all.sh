#!/bin/bash

export PYTHONPATH=$(pwd)

echo "Erase..."
coverage erase
rm -fr htmldoc 2>/dev/null

echo "Run..."

files=(utilities ldapfilter pelix ipopo)
for i in ${files[@]}
do
    echo "Working on $i"
    coverage run --source pelix --parallel-mode tests/${i}_test.py || exit 1
done

echo "Combine..."
coverage combine

echo "HTML..."
coverage html

echo "Done."
python -m webbrowser ./htmlcov/index.html
