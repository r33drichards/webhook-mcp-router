# In-process Go webhook fork evidence

Status: local patch prepared; runtime result **blocked before compilation**. No external fork, deployment, hooks, credentials, or payload forwarding.

## Source and concrete change

Fetched the official pinned archive:

```sh
curl -fLsS --max-time 30 https://github.com/adnanh/webhook/archive/2bbdeb9f90b5f98c7b7b8976881efd6da9f69571.tar.gz -o /tmp/ingress-source.tar.gz
tar -xzf /tmp/ingress-source.tar.gz --strip-components=1 -C spike/ingress/source
```

Fetch exited 0. Archive checksum and source URL are recorded in `spike/ingress/logs/source.json`. The source is preserved in `spike/ingress/source`; `spike/ingress/inprocess.patch` records modifications against that archive.

A new opt-in synthetic hook path verifies HMAC over bounded raw bytes before parsing. It snapshots policy/registered-subscription state, evaluates each policy with OPA's Go API, validates subscription IDs and bounded selected data, and writes only a dry-run response. It has no arbitrary URL routing or outbound sender. Per-policy errors and panics are isolated. Policies receive no network built-ins. Limits: 16 policies, 32 KiB per source, 100 subscriptions, 64 KiB request body, 100 ms per policy, 2-second request context, 16 KiB decision and at most 100 routes per policy. These are untested code paths, not proven safeguards.

Prepared tests assert malformed policy isolation, valid registered-ID selection, rejection of an arbitrary URL used as an ID, and signature rejection before JSON parsing. `gofmt` completed (exit 0).

## Executed build attempts

Working directory: `/workspace/webhook-mcp-router/spike/ingress/source`.

```sh
GOPROXY=off GOTOOLCHAIN=local \
GOPATH=/workspace/webhook-mcp-router/.tools/gopath \
GOCACHE=/workspace/webhook-mcp-router/.tools/gocache \
/workspace/webhook-mcp-router/.tools/go/bin/go test -mod=mod \
  -run 'TestPolicyIsolationAndRegisteredIDs|TestSignatureBeforeJSON' .
```

Exit **1**, setup failed: OPA v1.9.0 and several upstream dependencies are absent from the local module cache; `module lookup disabled by GOPROXY=off`. Exact output: `spike/ingress/logs/test-offline.log` and `.exit`.

```sh
GOPROXY=off GOTOOLCHAIN=local \
GOPATH=/workspace/webhook-mcp-router/.tools/gopath \
GOCACHE=/workspace/webhook-mcp-router/.tools/gocache \
GOOS=wasip1 GOARCH=wasm \
/workspace/webhook-mcp-router/.tools/go/bin/go test -mod=mod \
  -c -o ../ingress-tests.wasm .
```

Exit **1**, dependency setup failed. Exact output: `spike/ingress/logs/wasi-build-offline.log` and `.exit`. No Wasm test binary was produced; no Wasmer execution of this fork was attempted or passed.

The initial root-directory test invocation also failed because it was outside the Go module; preserved in `test-attempt.log/.exit`, then corrected as above. This was a command-location error, not a runtime result.

Offline mode deliberately avoids retrying/bypassing the already-observed OPA dependency download HTTP 403 in the parent runtime lane. No alternate OPA source fetch was attempted. No approval is pending, and there is no uncertain remote mutation.

## Smallest remaining steps

1. Obtain the exact pinned dependencies through an authorized permitted source, then compile and execute the prepared native and WASI tests.
2. Establish a host-reachable HTTP adapter for the chosen Wasmer mode; stock Go WASI's fake in-memory listener does not satisfy ingress.
3. Run a signed synthetic HTTP request through this actual fork under Wasmer, assert independent outcomes from two policies plus a failing one, and confirm the dry-run sink receives only registered IDs/bounded selected data.

The compiled OPA-Wasm C-host success elsewhere is a fallback result, not proof that this preferred in-process Go evaluator works.

Latest storage constraint: receiver registration/policy database access must be read-only; MCP owns read-write management. This patch implements no database access; the later combined-service extension exposes only synthetic process-local registration tools. The test-only snapshot replacement helper is not a database authorization implementation. Read-only DB enforcement remains to be tested separately.

## Combined-service extension

The local fork now includes `router_mcp.go`: one Go service handles webhook ingestion and an opt-in `/mcp` SDK route. Dependency pin: `github.com/modelcontextprotocol/go-sdk v1.8.1-0.20261023154812-2e00768cde3f`. Cached SDK source confirms `StreamableHTTPOptions.Stateless`, `JSONResponse`, generic `AddTool`, and `AddReceivingCustomMethod` APIs; no runtime wire test passed.

Synthetic create/list tools operate on process-local subscription IDs. A read-only interface is passed to receiver evaluation, while MCP has a write wrapper. This is logical separation only; no DB role enforcement or restart durability. Event catalog shape is scaffolded; subscribe/unsubscribe deliberately return an unsupported-live-lifecycle error rather than pretending callback activation.

After adding the SDK route, both native `go test -mod=mod -run 'TestPolicyIsolationAndRegisteredIDs|TestSignatureBeforeJSON' .` and `GOOS=wasip1 GOARCH=wasm go test -mod=mod -c -o ../combined-tests.wasm .` were attempted from the source directory. Both exited **1**, missing dependencies under `GOPROXY=off`; full outputs/exits are `spike/ingress/logs/combined-test-offline.*` and `combined-wasi-offline.*`. The environment matched earlier attempts plus `GOMODCACHE=/workspace/webhook-mcp-router/.tools/gomodcache` to reuse the authorized SDK source cache. No network fetch was attempted. No combined executable or Wasm artifact was produced.

The single-service source and patch are concrete but remain uncompiled/unexecuted. Do not claim MCP initialization, tool calls, callback lifecycle, persistence, or Wasmer HTTP compatibility from this skeleton.
