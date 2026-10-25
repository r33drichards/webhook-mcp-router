#!/usr/bin/env bash
# Provisional pinned-binary build; Nix release reproducibility remains outstanding.
set -euo pipefail
: "${WASIX_GO:?run the digest-verified compiler installer first}"
export GOTOOLCHAIN=local
repo_root=$(pwd)
(cd spike/hosted && "$WASIX_GO" mod verify && GOOS=wasip1 GOARCH=wasm CGO_ENABLED=0 "$WASIX_GO" build -mod=readonly -trimpath -o "$repo_root/deploy/server.wasm" .)
mkdir -p deploy/certs
# Public trust roots from the supported CI image. This is not a Nix-pinned CA build.
cp /etc/ssl/certs/ca-certificates.crt deploy/certs/ca-certificates.crt
sha256sum deploy/server.wasm deploy/certs/ca-certificates.crt
