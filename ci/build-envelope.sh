#!/usr/bin/env bash
set -euo pipefail
# First validates the unchanged official baseline and prepares identical manifests.
bash ci/build-official-wcgi.sh
rustc +1.85.0 --target wasm32-wasip1 -O -o deploy/server.wasm spike/cgi-envelope/main.rs
sha256sum deploy/server.wasm
wasmer validate deploy/server.wasm
wasmer inspect deploy/server.wasm
python3 ci/envelope-guest-check.py deploy/server.wasm
