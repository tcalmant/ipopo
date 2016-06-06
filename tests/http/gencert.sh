$#!/bin/bash

# Required
domain=ipopo.coderxpress.net
commonname=$domain
outputDir=$1

# Generate a random string as locality
# bash generate random 10 character alphanumeric string (lowercase only)
random=$(cat /dev/urandom | env LC_CTYPE=C tr -dc 'a-z0-9' | fold -w 10 | head -n 1)

#Change to your company details
country=FR
state=
locality=$random
organization=coderxpress.net
organizationalunit=ipopo
email=abuse@coderxpress.net
 
#Optional
password=hyperpassword
 
if [ -z "$outputDir" ]
then
    echo "outputDir argument not present."
    echo "Usage $0 [outputDir]"
 
    exit 99
fi

mkdir -p $outputDir
echo $random > $outputDir/random

echo "Generating key request for $domain"
 
#Generate a key
openssl genrsa -des3 -passout pass:$password -out $outputDir/$domain.key 2048 -noout
 
#Remove passphrase from the key. Comment the line out to keep the passphrase
echo "Removing passphrase from key"
openssl rsa -in $outputDir/$domain.key -passin pass:$password -out $outputDir/$domain.key
 
#Create the request
echo "Creating CSR"
openssl req -new -key $outputDir/$domain.key -out $outputDir/$domain.csr -passin pass:$password \
    -subj "/C=$country/ST=$state/L=$locality/O=$organization/OU=$organizationalunit/CN=$commonname/emailAddress=$email"
 
echo "---------------------------"
echo "-----Below is your CSR-----"
echo "---------------------------"
echo
cat $outputDir/$domain.csr
 
echo
echo "---------------------------"
echo "-----Below is your Key-----"
echo "---------------------------"
echo
cat $outputDir/$domain.key



