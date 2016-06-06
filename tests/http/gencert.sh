#!/bin/bash

# Required
domain=$1
commonname=$domain
outputDir=$2

#Change to your company details
country=FR
state=
locality=
organization=coderxpress.net
organizationalunit=ipopo
email=abuse@coderxpress.net
 
#Optional
password=hyperpassword
 
if [ -z "$domain" ]
then
    echo "domain argument not present."
    echo "Usage $0 [domain] [outputDir]"
 
    exit 99
fi

if [ -z "$outputDir" ]
then
    echo "outputDir rgument not present."
    echo "Usage $0 [domain] [outputDir]"
 
    exit 100
fi

mkdir -p $outputDir

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
