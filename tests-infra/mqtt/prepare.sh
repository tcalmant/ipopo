#!/bin/sh
# Generates the secrets of the test MQTT broker, before it starts: a test CA,
# the broker and client certificates of the TLS listeners, and the password of
# the test user (in .env, read by the broker and the tests).
# They are never committed: each checkout makes its own, kept until removed.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/certs"
DAYS=30
SUBJ="/C=FR/ST=Auvergne-Rhone-Alpes/L=Grenoble/O=iPOPO Tests"

if [ ! -f "$DIR/.env" ]; then
    umask 077
    printf 'MQTT_TEST_USERNAME=ipopo-test\nMQTT_TEST_PASSWORD=%s\n' "$(openssl rand -hex 16)" > "$DIR/.env"
    umask 022
    # The broker reads it as another user in its container
    chmod 644 "$DIR/.env"
fi

if [ -f "$OUT/ca.crt" ]; then
    exit 0
fi

mkdir -p "$OUT"
cd "$OUT"

openssl req -new -x509 -days $DAYS -nodes -newkey rsa:2048 \
    -subj "$SUBJ/CN=iPOPO Test MQTT CA" -keyout ca.key -out ca.crt \
    -addext "basicConstraints=critical,CA:true" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"

for name in server client; do
    if [ "$name" = server ]; then
        usage="serverAuth"
        san="subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1"
    else
        usage="clientAuth"
        san="subjectAltName=DNS:ipopo-test-client"
    fi

    openssl req -new -nodes -newkey rsa:2048 -subj "$SUBJ/CN=$name" \
        -keyout "$name.key" -out "$name.csr"
    printf '%s\n' "basicConstraints=CA:false" \
        "keyUsage=critical,digitalSignature,keyEncipherment" \
        "extendedKeyUsage=$usage" "authorityKeyIdentifier=keyid,issuer" \
        "$san" > "$name.ext"
    openssl x509 -req -days $DAYS -in "$name.csr" -CA ca.crt -CAkey ca.key \
        -CAcreateserial -extfile "$name.ext" -out "$name.crt"
    rm "$name.csr" "$name.ext"
done

# The CA key is only needed to sign: a new CA is made when the folder is removed
rm ca.srl ca.key
# The broker runs as another user in its container
chmod 644 ./*.key ./*.crt
