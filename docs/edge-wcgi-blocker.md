# Reproducible Edge WCGI blocker

## Observed result

Official-template reproduction [run 40166166069](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40166166069), source commit `245de875c23c442761c35cb115a3c6106e61aada`, failed on October 25, 2026 at 05:38:25 UTC. Native compilation, module validation and local Wasmer CGI execution passed. Hosted GET / returned HTTP 500 on all eight attempts from 05:37:42 through 05:38:20 UTC; bounded reads exceeded 65,536 bytes and did not match the expected greeting. Hosted POST was not attempted because the GET prerequisite failed.

This is a reproducible hosted package/platform/configuration blocker, not a proven Wasmer bug. Deployment acceptance does not prove successful runtime startup or active-version propagation. The precise failing layer remains unknown.

## Minimal reproduction already in this repository

- Upstream source: [wasmerio/wcgi-rust-template at ec51018](https://github.com/wasmerio/wcgi-rust-template/tree/ec51018faf125703b45b5f960b02b45887985e19), unchanged source/Cargo files and lockfile, licenses preserved in spike/official-wcgi.
- Compiler: Rust 1.85.0, target wasm32-wasip1, cargo build --locked --release.
- Module SHA256: `cfb524895407fd0117a32d9aa6fa536113f068ee29393c851c9de8b930417b90`.
- Module: 193.4 KiB; preview1 imports only (fd_read, fd_write, random_get, environ_get, environ_sizes_get, proc_exit); exports _start and __main_void; unshared memory initially 17 pages.
- Package: wasi ABI, https://webc.org/runner/wcgi, rfc-3875 dialect, upstream SCRIPT_NAME=rust_wcgi annotation.
- App: existing isolated r33drichards/webhook-mcp-router, canonical ID da_K6AIot5U1ND7; minimal kind/owner/name/package configuration. No service environment variables, certificate mapping or active volume mounts. Existing volumes were not deleted.
- Expected: GET / returns exactly Hello, World!; synthetic POST returns Hello, Synthetic!. Both bodies passed under local Wasmer 7.5.0, exit 0.
- Commands/config generation: ci/build-official-wcgi.sh; hosted assertions: ci/official-wcgi-check.py hosted; workflow: official-wcgi.yml. No new run should be dispatched without a concrete diagnostic hypothesis.

## Comparisons retained

| Candidate | Local Wasmer | Hosted |
|---|---|---|
| Official SDK + native OPA using WASIX Go | Full synthetic networking/event tests passed | Initialization failed |
| Credential-free health in integrated binary | Passed | 503 once, then seven 500s; run40164818062 |
| Constant standard-library CGI, WASIX Go1.25.5 | Passed | Eight 500s; run40165387023 |
| Identical constant CGI, stock Go1.25.5 preview1 only | Passed | Eight 500s; run40165762867 |
| Official Rust CGI, minimal configuration | Passed | Eight 500s; run40166166069 |

Removing SDK/OPA, WASIX-specific imports, and finally custom app mappings did not yield a successful hosted reply. This rules out those factors as sufficient explanations in these comparisons, not every possible interaction.

## Next diagnostic boundary and cleanup

Stop full-service retries and service-secret recreation. A useful next investigation would inspect the exact deployed package/active version and platform runtime diagnostics for the official-template attempt, or have the platform operator reproduce this minimal example. No support message has been sent and no external access change is authorized by this report.

The last credential-bearing test verified removal of all three Wasmer POC secrets, credential-free redeployment and live rejection of the old bearer at 05:04:40 UTC. Later probes checked approved service-secret names absent before/after deployment and never created any. App/package history and detached synthetic volumes remain; no deletion is claimed. Parent browser still owns removal of POC_TEST_TOKEN, POC_RECEIPT_TOKEN and POC_WEBHOOK_SECRET from GitHub environment wasmer-poc, leaving WASMER_TOKEN unchanged. Required cleanup deadline: October26 04:25 UTC.

No hosted MCP initialize, durable registration or callback-delivery success has been demonstrated. No real GitHub webhook was configured. No paid upgrade or new credential was requested during the baseline tests.
