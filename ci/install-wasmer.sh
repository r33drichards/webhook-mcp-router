#!/usr/bin/env bash
set -euo pipefail
# Official release asset, version and archive digest from the runtime evidence.
wasmer_root="${RUNNER_TEMP:?}/wasmer-7.5.0"
mkdir -p "$wasmer_root"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  https://github.com/wasmerio/wasmer/releases/download/v7.5.0/wasmer-linux-amd64.tar.gz \
  -o "$wasmer_root/archive.tar.gz"
printf '%s  %s\n' 23f99818deaad93859f8bb8292af81f0c39f25aea19eaccfb72fc7c9e8a3fae9 "$wasmer_root/archive.tar.gz" | sha256sum --check
tar -xzf "$wasmer_root/archive.tar.gz" -C "$wasmer_root"
printf '%s\n' "$wasmer_root/bin" >> "$GITHUB_PATH"
printf 'WASMER_DIR=%s\n' "$wasmer_root" >> "$GITHUB_ENV"
WASMER_DIR="$wasmer_root" "$wasmer_root/bin/wasmer" --version
