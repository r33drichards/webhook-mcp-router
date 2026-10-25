# Official example provenance

Upstream: https://github.com/wasmerio/wcgi-rust-template/tree/ec51018faf125703b45b5f960b02b45887985e19 (November 17, 2023).
Cargo.toml, Cargo.lock, src/main.rs, README.md and both license files are copied unchanged from that commit. The source echoes a synthetic body as Hello, <body>!, defaulting to World. This is the official template linked by the current Wasmer WCGI guide; its age is recorded, not represented as a recent runtime certification.

Build pins Rust1.85.0 and uses the locked dependencies. The target name is wasm32-wasip1 (current name corresponding to upstream wasm32-wasi). ci/build-official-wcgi.sh reproduces upstream runner/dialect and SCRIPT_NAME annotation, adapting only package ownership/version/artifact path and omitting descriptive repository/readme metadata. The app manifest is upstream's minimal kind/name/package form plus our explicit authorized owner. No certificate filesystem mapping, application env or volume mounts are included. Existing remote volumes are not deleted; this diagnostic removes their mounts from the active app configuration.

This comparison changes language and configuration together to establish an official baseline. A pass would require follow-up one-variable comparisons to identify which prior difference mattered. No native OPA architecture switch is implied.
