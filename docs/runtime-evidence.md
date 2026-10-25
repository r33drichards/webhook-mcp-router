## Synthetic hosted fixture implementation checkpoint

Added `spike/hosted`: official pinned SDK CGI entrypoint, authenticated synthetic create/list/delete/emit tools, separate registration and receipt directories, fixed HTTPS sink, Standard Webhooks raw-byte HMAC verification before parsing, timestamp bounds and write-once replay rejection. This is a focused fixture, not the combined OPA service or complete events extension (discovery/challenge/TTL/cursor remain incomplete). No public endpoint or secret was configured.

Executed `GOCACHE=$PWD/.tools/gocache GOPATH=$PWD/.tools/gopath GOTOOLCHAIN=local GOPROXY=off .tools/go/bin/go test spike/hosted/core.go spike/hosted/core_test.go`: exit 0, `ok command-line-arguments 0.016s`. Tests include a real native loopback TLS callback, fresh-object file readback, verified receipt, raw-body tamper rejection, stale timestamp rejection and replay rejection. These are native stdlib tests, not SDK/Wasmer passes.

Executed official SDK tests in `spike/hosted` with project-local Go/cache, `GOPROXY=off`, `go test -mod=mod ./...`: exit 1 during setup; `github.com/segmentio/encoding@v0.5.4` lookup disabled/offline and absent. No denied download retried. The SDK fixture has not compiled. Independent CI job now resolves verified modules, runs SDK native tests, builds WASI, and runs `ci/sdk-cgi-check.py` to assert initialize/tools/create/readback across fresh Wasmer instances. Those CI assertions have not run. YAML and Python syntax checks passed. Deployment readiness remains false; protected/manual cost and auth gates remain unchanged.

# Local Wasmer runtime feasibility evidence

Synthetic local spike, 2026-10-25. No production hooks, accounts, credentials, deployment, publication, or external payload delivery.

## Executed policy result

OPA-compiled policy **actually executed inside Wasmer 7.5.0** through its official C API library. The host is a native C executable, not a Go guest and not Wasmer Edge.

- Matching synthetic event: exactly `[{"result":["sub_match"]}]`, exit 0.
- Non-matching synthetic event: exactly `[{"result":[]}]`, exit 0.
- Native OPA evaluation returned identical decisions for both inputs.
- Malformed JSON was rejected, exit 1.
- The host checks that the policy requires no host built-ins, denies builtin/abort callbacks, imports no WASI/network functions, caps imported memory at 8 MiB, and bounds input at 64 KiB. The test driver applies a 30-second process timeout. This limited probe is not a hardened reusable policy host.

Exact commands, stdout, stderr, inputs, and exit codes: [OPA/Wasmer log](runtime-logs/opa-wasmer-evidence.json). Reproduce from project root:

```sh
python spike/router/run_wasmer_policy.py
```

This runs OPA `build -t wasm -e router/subscription_ids` with the restricted capabilities file, compiles the C host against the official Wasmer library with `-Wall -Wextra -Werror`, executes both fixtures, compares native results, and asserts malformed-input rejection. The policy is `policies/routes.rego`; host source and fixtures are under `spike/router/`.

## Tool provenance and setup

- Wasmer 7.5.0: official `wasmerio/wasmer` GitHub release, Linux amd64 archive SHA-256 `23f99818deaad93859f8bb8292af81f0c39f25aea19eaccfb72fc7c9e8a3fae9`, verified before extraction. Release metadata obtained through the authorized GitHub connector.
- Initial `wasmer --version` exited 101 because its default config directory was read-only. Setting `WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer` resolved this; subsequent version/run commands succeeded. No filesystem permission changes were made.
- OPA 1.9.0: official release, Linux static binary SHA-256 `66fa66f3b730b2fb086003863428b382b2898d343adb4b5dfab5598b4d739eed`, verified against the published checksum. `opa version` reports Go 1.25.1 and build commit `c49e670294e45bb3fd76b9e945cf821478a4bbfc`.
- Go 1.27.3: official go.dev download, SHA-256 `65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40`, verified by the MCP probe lane. `/usr/bin/go` was a board-game executable, not the compiler. The installed compiler is `.tools/go/bin/go`.
- Tool installations stayed under the separate project's ignored `.tools` directory. Preloaded `mcp-js` remained unchanged.

## Go embedded Rego route: blocked before compilation

A small Go router using `github.com/open-policy-agent/opa/v1/rego` at v1.9.0 was prepared. Commands used:

```sh
export PATH=/workspace/webhook-mcp-router/.tools/go/bin:$PATH
export GOPATH=/workspace/webhook-mcp-router/.tools/gopath
export GOCACHE=/workspace/webhook-mcp-router/.tools/gocache
export GOTOOLCHAIN=local
cd spike/router
go mod tidy
go build -o router-native .
GOOS=wasip1 GOARCH=wasm go build -o router.wasm .
```

`go mod tidy` exited 1 because the module proxy's redirect to `storage.googleapis.com` returned HTTP 403 for the OPA v1.9.0 archive. Both subsequent builds exited 1 with a missing go.sum entry. [Download log](runtime-logs/router-tidy.log), [native build](runtime-logs/router-native-build.log), [WASI build](runtime-logs/router-wasi-build.log); corresponding `.exit` files record statuses. Expiring query parameters were redacted from the shared log.

No alternate route was used to bypass this network denial. Therefore neither native nor WASI embedded-Go Rego evaluation was established. Smallest prerequisite: make the exact required module sources available through an authorized dependency path, then rerun the build and tests. The compiled-policy C-host result is independent evidence, not a substitute claim that this Go path passed.

## Go MCP, network, subprocess, and storage lane

See [MCP runtime evidence](mcp-runtime-evidence.md) and `spike/mcp/logs/` for the exact probes. The SDK dependency download is also blocked by HTTP 403. A stdlib-only Go WASI probe provides independent boundary tests; it is not the official SDK server.

The requested full chain remains distinct: **Go ingress HTTP listener → packaged Go router subprocess → OPA evaluation**. A failed subprocess primitive invalidates that unchanged chain. Moving business logic in-process removes the subprocess requirement but still needs real host-reachable HTTP and executable OPA integration. No native-only or in-guest fake-network result proves that fallback.

## Nix lane

Pinned build/patch definition and dependency metadata are in `spike/nix/`. [Nix evidence](nix-runtime-evidence.md) records the absent `nix`, `nix-instantiate`, and `/nix` prerequisites. No Nix evaluation or build ran; `vendorHash` is deliberately required rather than fabricated. This is a prepared path, not a reproducible-build claim.

## Scope of conclusions

Policy Wasm execution is proven locally. The full Go ingress/router/MCP pipeline and Wasmer Edge deployment are not. No external authorization or live deployment was attempted. There is no pending approval or uncertain remote mutation; the outstanding failures are local runtime capability and dependency/tooling prerequisites.

## Latest scope decision

The user stopped subprocess work and selected a local Go webhook fork/patch with OPA's native Go API in-process. Every request snapshots registered policies and evaluates each; results choose registered subscription IDs and bounded payloads for a synthetic sink. The latest consolidation selects one Go service, including official SDK MCP routes. The embedded evaluator remains primary, despite its dependency blocker; the successful compiled-policy Wasmer host is fallback evidence only. Existing subprocess diagnostics are retained, not pursued further. The new patch and its exact validation state are recorded separately in `docs/ingress-runtime-evidence.md` as prepared, with build blockers explicit.

## Combined service and database update

The latest target is ONE Go service embedding the webhook fork, OPA native Go evaluator, and official Go MCP HTTP routes. OpenAI-style MCP Events uses webhook delivery; no persistent client connection is required by that intended delivery mode. Stateless MCP HTTP/JSON settings are supported in SDK source but the SDK flow has not run. Separate database credentials/handles enforce read-only ingestion and read-write MCP control at the DB/gateway, but same-process access is logical separation, not a complete credential isolation boundary.

Actual outbound tests now complete: native HTTP GET and raw TCP echo passed; the stock Go WASI guest under Wasmer failed HTTP with exit 45 and TCP with exit 47, both connection refused despite explicit loopback permission. Host counters confirm no guest request arrived. [Exact outbound log](../spike/mcp/logs/outbound-runtime.json). HTTP database APIs therefore do not bypass this tested networking limitation. [Storage comparison](storage-options.md) remains a design assessment; no database driver, TLS, SQL transaction, or remote database was tested.

## Prepared combined-service patch

`spike/ingress/inprocess.patch` now includes in-process per-policy routing and opt-in official Go SDK `/mcp` routes with stateless JSON responses. Synthetic create/list tools share process-local registration state through logical read/write interfaces. The patch rejects live event subscription lifecycle operations rather than activating unverified callbacks. Native and WASI compilation attempts both exit 1 during missing-dependency setup; the source is concrete but uncompiled. See [ingress evidence](ingress-runtime-evidence.md). No complete combined-service runtime, durable MCP registration, or live delivery result is claimed.

## Bounded networking diagnosis (documentation/source only)

No denied download was retried and no implementation was expanded during this follow-up.

The observed failures are consistent with **standard Go WASI limitations**, not a claim that Wasmer itself lacks networking. The installed Go 1.27.3 `src/net/net_fake.go` explicitly builds for `js || wasip1` and implements fake in-memory sockets. Wasmer documents Go's standard WASI target separately from WASIX, whose compatible guests can use sockets and process facilities. No official supported Go-to-WASIX networking toolchain for this exact Go 1.27.3 / Wasmer 7.5.0 / Edge combination was verified in this bounded review. [Wasmer WASIX language guidance](https://docs.wasmer.io/runtime/wasix/), [Go WASI limitations](https://go.dev/blog/wasi).

The frequently cited `stealthrocket/net` project now redirects to `dispatchrun/net`. Its own README promises compatibility with **WasmEdge and wasi-go/Timecraft**, not Wasmer. It supplies replacement listeners/dialers; even there, ordinary `http.ListenAndServe` continues to use the standard network package. Do not install it on the assumption that all WASI socket extension ABIs are interchangeable. Inspected source revision: `fc22d416b6627bfd846e773720242ad5a87376d0`; the tree includes `wasip1/syscall_wasmedge_wasip1.go`. No package download/build/runtime test was attempted. [Adapter README](https://github.com/dispatchrun/net/blob/fc22d416b6627bfd846e773720242ad5a87376d0/README.md).

### Smallest documented inbound alternative

Wasmer Edge explicitly distinguishes **Proxy** mode, which expects a WASIX server listening on a port, from **WCGI**, which creates a fresh WASI instance per request and supplies request metadata/body through environment/stdin and receives the response through stdout. WCGI therefore avoids the guest-listener requirement. This is an actual documented Edge mode, not a custom networking workaround. [Edge deployment modes](https://docs.wasmer.io/edge/learn/deployment-modes/), [WCGI runner](https://docs.wasmer.io/runtime/runners/wcgi/).

The smallest proposed adaptation is one Go program calling `net/http/cgi.Serve` on the combined webhook/MCP mux instead of `ListenAndServe`; OPA remains in-process. Go documents that `cgi.Serve` runs an `http.Handler` against the current CGI request. This is the **guest-side Serve function**, not Go's CGI host Handler that launches subprocesses. A request/response MCP configuration (`Stateless` + `JSONResponse`) is a plausible fit, but exact protocol headers, notification responses, raw body/signature preservation, request metadata, and host compatibility still require tests. The synthetic loopback guard in the current patch would need deliberate CGI-aware handling; do not simply remove it and expose unauthenticated management. [Go CGI Serve](https://pkg.go.dev/net/http/cgi#Serve).

**Not proven:** Go+OPA compilation, WCGI execution of this service, official SDK initialization/tool calls, or Wasmer Edge behavior. WCGI solves neither outbound TCP/HTTP nor shared DB access nor webhook delivery. Fresh instances also discard process-local registration and compiled-policy caches, so startup cost and durable storage remain relevant. Keep this as the next bounded experiment after dependency access is fixed, not an assertion that the entire architecture is viable.

A native Go combined process remains a fallback if Wasmer is optional. If Wasmer is mandatory, require a verified outbound host API/compatible guest integration for database and callback traffic before committing to the complete design. Do not silently substitute a separate worker/runtime or another language for the selected one-service architecture.

## Shared database comparison (consolidated)

| Candidate | Enforceable access split | Runtime and operational tradeoff |
| --- | --- | --- |
| PostgreSQL behind a narrow HTTPS API, such as PostgREST | Distinct credentials map to a SELECT-only routing role and scoped MCP write role; restrict RPCs and inherited grants too | Gateway handles pooling; per-request transaction can return one versioned policy/registration snapshot. Still needs working guest outbound HTTP/TLS; WCGI does not supply it automatically. |
| Direct PostgreSQL TCP/TLS | Separate DB roles: ingestion SELECT only, MCP scoped writes, neither owner/superuser | Needs proven TCP/DNS/TLS and driver support. Bound pools or use a pooler to avoid cold-start connection multiplication. Native control success is not guest driver proof. |
| SQLite on local/mounted storage | Read-only connection plus filesystem permission constraints; same process with RW access can bypass a convention | Useful single-host synthetic option. Local file persistence does not prove concurrent DB semantics. Wasmer's current RWX volume model and SQLite WAL's same-host requirements make autoscaled shared SQLite an unsafe assumption. |

Use the **same durable registration/policy DB** through RO ingestion and RW MCP handles. These are logical least-privilege boundaries inside one Go process, not complete credential isolation. Read policy versions and registrations consistently, activate versions atomically, and cache immutable versions with explicit freshness. Keep callback secrets out of OPA and receiver-readable views unless explicitly required. Keep intake/outbox and delivery-write permissions separate; never grant registration writes to ingestion just to record retries. No database, driver, TLS session, SQL grants, or remote credentials were tested/configured.

Primary references: [PostgREST roles](https://docs.postgrest.org/en/v13/references/auth.html), [PostgREST transactions](https://docs.postgrest.org/en/v13/references/transactions.html), [PostgreSQL privileges](https://www.postgresql.org/docs/current/sql-grant.html), [Wasmer volume limitations](https://docs.wasmer.io/edge/learn/volumes/), [SQLite WAL](https://www.sqlite.org/wal.html).

## Exact dependency-fetch blockers (no credentials)

The stable module request URLs are:

```text
https://proxy.golang.org/github.com/open-policy-agent/opa/@v/v1.9.0.zip
https://proxy.golang.org/github.com/segmentio/encoding/@v/v0.5.4.zip
```

The observed HTTP 403 occurred at these redirected object paths on `storage.googleapis.com`:

```text
https://storage.googleapis.com/proxy-golang-org-prod/3ec1737e2cf5403c-github.com:open-policy-agent:opa-v1.9.0.zip
https://storage.googleapis.com/proxy-golang-org-prod/9ee04aa9d882e669-github.com:segmentio:encoding-v0.5.4.zip
```

The actual redirect URLs also contained temporary signed query parameters; those are intentionally omitted/redacted. The paths above are diagnostic identifiers, not guaranteed reusable download URLs. `proxy.golang.org` issued redirects; the observed failing host was `storage.googleapis.com`. Go module verification remained enabled. Later fork builds used `GOPROXY=off` and failed because dependencies were missing, not because the code compiled and failed at runtime. No alternate route, proxy change, verification bypass, credential change, or policy change was attempted. An environment operator can legitimately investigate permitted access to the standard module flow; this report does not request broad network access or supply signed URLs.

## WCGI local-runner checkpoint

The requested minimal Go `net/http/cgi` inbound test stopped at the runner prerequisite. The installed Wasmer CLI reports **7.5.0**; `wasmer run --help` exposes no WCGI serving option. More decisively, the official [CGI apps on Wasmer Edge guide](https://docs.wasmer.io/edge/guides/wcgi-on-edge/) states that local `wasmer run` cannot execute WCGI packages and tests its example by deploying to Edge. Its manifest selects `https://webc.org/runner/wcgi` with the `rfc-3875` dialect. This is a runner identifier, not a dependency download attempted here.

Initial prerequisite inspection executed `wasmer --version`, `wasmer run --help`, and `go version`, all exit 0, using the project-local binaries and writable `WASMER_DIR`. Exact argv, stdout, stderr, and exit codes are saved in [wcgi-prerequisite.json](runtime-logs/wcgi-prerequisite.json). Go remains 1.27.3. No synthetic HTTP request reached a WCGI host; the separately authorized guest-only probe below does not establish a functioning local WCGI HTTP runner.

**Exact blocker:** a supported local WCGI HTTP runner is not available in the inspected installed CLI/documented local flow. The smallest prerequisite is such a local runner; the documented alternative is an Edge deployment, which is outside authorization. Per the instruction to stop if the runner is unavailable, no runner installation, dependency retry, account configuration, or deployment was attempted. This is a tooling/scope stop, not an automatic approval denial or an uncertain remote action.

WCGI remains a documented inbound architectural option only. It does not establish combined Go/OPA/MCP compatibility, outbound DB or callback connectivity, or durable registration behavior. The earlier compiled-policy Wasmer success and standard-Go guest networking failures remain unchanged.

### Subsequent authorized generic CGI guest probe: PASS, limited scope

Following the instruction to finish an independent generic CGI probe while SDK downloads remain blocked, compiled `spike/wcgi/main.go` using Go's standard library only, `GOOS=wasip1 GOARCH=wasm GOTOOLCHAIN=local GOPROXY=off`. Build exit 0. The resulting guest ran under installed Wasmer 7.5.0, exit 0. The test manually supplied CGI metadata through `--env` and the synthetic body through stdin. `cgi.Serve` invoked the Go `http.Handler`, emitted `Status: 200 OK`, and returned JSON. Assertions passed for exact POST method, `/synthetic` path, body including its trailing newline, and the synthetic header value. Exact build/run argv, stdin, stdout, stderr, exit codes and assertion are in [cgi-guest.json](runtime-logs/cgi-guest.json).

This proves guest-side Go CGI request parsing and response serialization under Wasmer without a guest network listener. It does **not** test the WCGI host's actual HTTP-to-CGI mapping, raw webhook signature validation, MCP, OPA integration, outbound connections, or durability. No WCGI host was installed and no deployment occurred.

**Official SDK stage remains blocked before compilation:** the existing SDK dependency `github.com/segmentio/encoding@v0.5.4` was unavailable after its recorded HTTP 403; no permitted new dependency supply was provided and no download was retried. Therefore MCP initialize, tools/list, tools/call, synthetic subscription creation, and fresh-instance registration readback have not run through CGI or WCGI. SDK source supports `Stateless: true` and `JSONResponse: true`; these avoid requiring a persistent session/SSE channel for the intended request/response flow, but source inspection is not protocol execution. Persistent registration would still need storage external to the per-request instance. Both a runnable WCGI host and the missing verified dependency supply are prerequisites for the requested full test.
## Hosted deployment authorization and prerequisite checkpoint

The user subsequently authorized ONE minimal synthetic hosted Go events MCP WCGI POC, superseding the earlier blanket no-deployment restriction. This does not authorize paid resources, new credentials/grants, access expansion, real payloads, or unauthenticated arbitrary callback registration. Earlier no-deployment statements describe actions taken at their respective stages.

Preflight result: `WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer /workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer whoami` exited **1**. The request to `https://registry.wasmer.io/graphql` failed with `hyper_util::client::legacy::Error(Connect, TunnelUnsuccessful)` / `tunnel error: unsuccessful`. No successful account lookup occurred. The checked process has no `WASMER_TOKEN`; neither the default `~/.wasmer/wasmer.toml` nor project `.tools/wasmer/wasmer.toml` exists. Only presence was inspected; no credential values were printed. This establishes missing CLI access here, not absence of a user account elsewhere.

The [official pricing page](https://wasmer.io/pricing) lists a free Hobby tier and a $10/month Pro tier. The actual account plan, remaining free allowance, storage eligibility, and billing exposure could not be verified. No paid resource was requested or created. A generic public free-tier listing is insufficient to assert this deployment costs zero for the user's account.

**Current blockers:** (1) permitted connectivity to the registry GraphQL endpoint; (2) an existing authorized account context available to this execution environment, without creating new credentials/grants; (3) the previously denied official SDK module dependency supply; (4) a controlled authenticated synthetic callback destination and a proven outbound transport; (5) durable registration storage within a verified no-spend allowance. No account configuration, login, deployment, new callback registration, or hosted request was attempted. The read-only preflight failed; it was not an automatic approval rejection and there is no pending or uncertain remote write. No alternate network route was tried.

The concrete pending action, once prerequisites are satisfied, is a single synthetic WCGI app deployment with restricted management access, official SDK stateless JSON request handling, persistent synthetic registration, and delivery exclusively to an approved test sink. Target namespace/app name and cost remain unresolved because account inspection failed. Hosted initialize, tools/list, registration call, fresh-invocation readback, and verified webhook receipt are all **not run**. The earlier generic CGI guest pass remains valid but does not substitute for these results.

## GitHub Actions preparation and publication checkpoint

Prepared `.github/workflows/build.yml` and `.github/workflows/deploy.yml` locally, with supporting scripts in `ci/` and bootstrap instructions in `docs/ci-bootstrap.md`. Official checkout/setup-go actions are pinned to connector-verified commit SHAs. Build CI uses no secrets; manual deployment uses a protected environment and fails closed before credentials/deployment while hosted readiness is false. The actual combined service, durable storage, authenticated WCGI entrypoint and receipt sink are not yet ready. The hosted E2E script is a concrete assertion client for a documented future synthetic fixture contract, not an implemented service or an E2E result. Nix remains the release-build goal; its bootstrap/vendorHash have not been validated.

Local checks: `bash -n ci/install-wasmer.sh` and Python compilation succeeded; both workflow YAML documents parsed with installed PyYAML (not GitHub's semantic validator). `ci/cgi-check.py` ran against installed Go/Wasmer with `GOPROXY=off` and passed exact method/path/body/header assertions. `ci/deployment-gate.py` exited 1 as intended and listed missing hosted implementation prerequisites. No dependency download was retried locally. No workflow has run remotely.

Public repository name/visibility is now authorized as `r33drichards/webhook-mcp-router`. Read-only connector lookup returned HTTP 404; no repository creation action is exposed. No publication occurred. Publication-candidate scan found no common credential tokens/private keys, signed cloud URL query parameters, Library IDs, or private thread identifiers. This is a targeted scan, not a guarantee that arbitrary secrets are absent. Generated CGI Wasm was excluded with `.gitignore`; toolchains/caches remain excluded. Upstream source licenses and example fixtures remain intact. Preloaded `/workspace/mcp-js` remains clean.

