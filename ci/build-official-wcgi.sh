#!/usr/bin/env bash
set -euo pipefail
rustup toolchain install 1.85.0 --profile minimal --no-self-update --target wasm32-wasip1
rustc +1.85.0 --version
cargo +1.85.0 build --locked --release --target wasm32-wasip1 --manifest-path spike/official-wcgi/Cargo.toml
cp spike/official-wcgi/target/wasm32-wasip1/release/wcgi-rust-template.wasm deploy/server.wasm
# Reproduce upstream manifest, changing namespace/version and artifact path only.
cat > deploy/wasmer.toml <<'TOML'
[package]
name = "r33drichards/webhook-mcp-router"
version = "0.0.1"
description = "Official Wasmer WCGI template reproduction"
license = "MIT OR Apache-2.0"

[[module]]
name = "server"
source = "server.wasm"
abi = "wasi"

[[command]]
name = "server"
module = "server"
runner = "https://webc.org/runner/wcgi"

[command.annotations.wasi]
env = ["SCRIPT_NAME=rust_wcgi"]

[command.annotations.wcgi]
dialect = "rfc-3875"
TOML
cat > deploy/app.yaml <<'YAML'
kind: wasmer.io/App.v0
owner: r33drichards
name: webhook-mcp-router
package: .
YAML
sha256sum deploy/server.wasm
wasmer validate deploy/server.wasm
wasmer inspect deploy/server.wasm
python3 ci/official-wcgi-check.py guest deploy/server.wasm
