#!/usr/bin/env bash
# Throwaway TLS for the E2E LLM stub: a one-day CA and a server certificate for the host name llm-stub.
#   bash tests/e2e/llm-stub/make-tls.sh <dir>      -> <dir>/ca.pem, <dir>/server.pem, <dir>/server-key.pem
# The assistant trusts only ca.pem (SSL_CERT_FILE) inside the E2E stack. Nothing here is a secret worth keeping:
# the files live under reports/ (git-ignored) and the key is regenerated on every run.
set -euo pipefail
dir="${1:?usage: make-tls.sh <dir>}"
mkdir -p "$dir"
cd "$dir"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=e2e-llm-stub-ca" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout ca-key.pem -out ca.pem 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=llm-stub" -keyout server-key.pem -out server.csr 2>/dev/null
printf '%s\n' "basicConstraints=critical,CA:FALSE" "keyUsage=critical,digitalSignature,keyEncipherment" \
  "extendedKeyUsage=serverAuth" "subjectAltName=DNS:llm-stub,DNS:localhost" \
  "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer" > server.ext
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -days 1 -sha256 \
  -extfile server.ext -out server.pem 2>/dev/null
rm -f server.csr server.ext ca.srl ca-key.pem
chmod 644 ca.pem server.pem server-key.pem   # read by the containers' non-root user; throwaway
