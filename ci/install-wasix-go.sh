#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$RUNNER_TEMP/wasix-go"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 https://github.com/wasix-org/go/releases/download/go1.25.5-6-wasix/go-1.25.5-linux-x86_64.tar.gz -o "$RUNNER_TEMP/wasix-go.tar.gz"
printf '%s  %s\n' c728bcffd6536f38125a652ada1da814bcf46c8cae974a873ab8f402f8d95ed0 "$RUNNER_TEMP/wasix-go.tar.gz" | sha256sum --check
tar -xzf "$RUNNER_TEMP/wasix-go.tar.gz" -C "$RUNNER_TEMP/wasix-go"
# Locate the archive's actual toolchain layout; require one Go compiler.
mapfile -t compilers < <(find "$RUNNER_TEMP/wasix-go" -type f -path '*/bin/go')
test "${#compilers[@]}" = 1
printf 'WASIX_GO=%s\n' "${compilers[0]}" >> "$GITHUB_ENV"
