#!/usr/bin/env bash
set -euo pipefail
: "${WASIX_GO:?run pinned WASIX Go installer}"
GOTOOLCHAIN=local GO111MODULE=off GOOS=wasip1 GOARCH=wasm CGO_ENABLED=0 "$WASIX_GO" build -trimpath -o deploy/server.wasm spike/constant-cgi/main.go
# Keep package filesystem and runner configuration identical to the service.
mkdir -p deploy/certs
cp /etc/ssl/certs/ca-certificates.crt deploy/certs/ca-certificates.crt
sha256sum deploy/server.wasm
wasmer validate deploy/server.wasm
wasmer inspect deploy/server.wasm
python3 ci/startup-guest-check.py deploy/server.wasm constant
