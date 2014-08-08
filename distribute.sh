#!/bin/bash

export PYTHONPATH="."

USER="coderxpress"
SERVER="coderxpress.net"
REMOTE_DIR=www-ipopo

# iPOPO Version
VERSION="0.5.7"

# Directories
API_HTML="api"
API_PDF="api-pdf"

# Files
DIST_DIR="dist"
DIST_TGZ="iPOPO-$VERSION.tar.gz"
DIST_ZIP="ipopo-$VERSION.zip"
TEST_ZIP="ipopo-$VERSION-tests.zip"
HTML_ZIP="ipopo-$VERSION-doc-html.zip"
PDF_FILE="ipopo-$VERSION-doc.pdf"
PDF_ZIP="ipopo-$VERSION-doc-pdf.zip"

LATEST_DIST_LINK="ipopo-latest.zip"
LATEST_TEST_LINK="ipopo-latest-tests.zip"
LATEST_HTML_LINK="ipopo-latest-doc-html.zip"
LATEST_PDF_LINK="ipopo-latest-doc-pdf.zip"

# Generate the API
echo "API..."
echo "... HTML ..."
epydoc --html pelix -o "$API_HTML" || exit 1

echo "... PDF ..."
epydoc --pdf pelix -o "$API_PDF" || exit 1

# Compress API files
echo "API Compression..."
echo "... HTML ..."
zip -r "$HTML_ZIP" "$API_HTML" || exit 1

pushd $API_PDF
echo "... PDF ..."
mv "api.pdf" "$PDF_FILE"
zip "$PDF_ZIP" "$PDF_FILE" || exit 1
popd
mv "$API_PDF/$PDF_ZIP" . || exit 1

# Clean up API folders
echo "API clean up..."
rm -fr "$API_HTML"
rm -fr "$API_PDF"

# Test files
echo "Unit tests..."
find tests -name '*.py' -print | zip "$TEST_ZIP" -@

# Python distribution
echo "Python source distribution..."
python setup.py sdist

# Convert the .tgz file into a .zip file
pushd "$DIST_DIR"
echo "... Extracting ..."
tar xf $DIST_TGZ || exit 1

echo "... Adding license ..."
cp ../LICENSE "iPOPO-$VERSION"

echo "... Zipping ..."
zip -r "$DIST_ZIP" "iPOPO-$VERSION"
popd
mv "$DIST_DIR/$DIST_ZIP" .

# Clean up
echo "Clean up distribution..."
rm -fr $DIST_DIR
rm MANIFEST

# Send to CoderXpress
echo "Creating SFTP script..."
BATCH_FILE=$(mktemp)
REMOTE_SHELL="remote_dist_ipopo_$VERSION.sh"
files=("$HTML_ZIP" "$PDF_ZIP" "$DIST_ZIP" "$TEST_ZIP")
for file in ${files[@]}
do
    echo "put '$file'" >> $BATCH_FILE
done
echo "put '$REMOTE_SHELL'" >> $BATCH_FILE

# Make the remote script
echo "Creating remote script..."
cat > "$REMOTE_SHELL" <<END
echo "Moving files..."
mkdir -p $REMOTE_DIR/dl
mv "$DIST_ZIP" "$REMOTE_DIR/dl/"
mv "$TEST_ZIP" "$REMOTE_DIR/dl/"
mv "$HTML_ZIP" "$REMOTE_DIR/dl/"
mv "$PDF_ZIP" "$REMOTE_DIR/dl/"

pushd $REMOTE_DIR
echo "Replacing API..."
rm -fr "$API_HTML"
unzip "dl/$HTML_ZIP"

echo "Making latest links..."
cd dl
ln -sf $DIST_ZIP $LATEST_DIST_LINK
ln -sf $TEST_ZIP $LATEST_TEST_LINK
ln -sf $HTML_ZIP $LATEST_HTML_LINK
ln -sf $PDF_ZIP $LATEST_PDF_LINK
popd
END

echo "Sending files..."
# Batch mode info :
# http://www.derkeiler.com/Newsgroups/comp.security.ssh/2007-06/msg00142.html
sftp -o "batchmode no" -b $BATCH_FILE $USER@$SERVER
rm $BATCH_FILE
rm $REMOTE_SHELL

# Remote script
echo "Remote commands..."
ssh $USER@$SERVER REMOTE_SHELL="$REMOTE_SHELL" "bash -s" <<'ENDSSH'
echo "On remote site - REMOTE SHELL = $REMOTE_SHELL"
bash "$REMOTE_SHELL"
rm "$REMOTE_SHELL"
ENDSSH

echo "All done"
