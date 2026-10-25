# Go MCP / networking / subprocess runtime spike

Date: 2026-10-25. Synthetic local tests only. No external payload forwarding or Wasmer Edge deployment.

## Results

| Stage | Actual result | Limit |
|---|---|---|
| Go JSON stdin/stdout under local Wasmer | PASS, exit 0 | Standard-library guest only; not OPA or MCP |
| Go HTTP self-loopback inside the guest | PASS, exit 0 | **Go's fake in-memory network**, not host networking |
| Host HTTP to native Go listener | PASS, HTTP 200 `synthetic-ok`, process exit 0 | Native positive control |
| Host HTTP to Wasmer Go listener | Connection refused despite guest ready marker and explicit loopback `--net` permission; guest exit 0 | Stock Go guest did not expose an OS listener |
| Go guest `os/exec` with CombinedOutput | FAIL, exit 43: `pipe: Not implemented on wasip1` | No router subprocess launched |
| Fresh guest write/read of subscription JSON | PASS, separate Wasmer processes both exit 0 | Preopened local directory only; not MCP, database, Edge, or multiwriter proof |
| Official Go SDK source pin | Downloaded | Source inspection only |
| Official SDK dependency resolution | FAIL, exit 1: segmentio/encoding v0.5.4 download HTTP 403 | Native/guest SDK execution not reached; no bypass attempted |
| MCP HTTP initialize → tool registration → fresh-instance read | NOT RUN | SDK dependency resolution blocked; real stock-Go HTTP also failed |

An early internal checkpoint initially interpreted the in-guest HTTP pass as networking success. Source inspection caught Go's fake networking implementation and a host-to-guest test disproved real reachability. Only the corrected conclusion above is valid.

## Versions and acquisition

- Official Go 1.27.3, downloaded from `https://go.dev/dl/go1.27.3.linux-amd64.tar.gz`.
- SHA-256 matched the official `https://go.dev/dl/?mode=json` metadata: `65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40`.
- Compiler path: `/workspace/webhook-mcp-router/.tools/go/bin/go`.
- Local Wasmer 7.5.0, installed by the parent investigation at `.tools/wasmer/bin/wasmer`.
- `WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer` for every guest execution.
- Official MCP SDK commit `2e00768cde3f1ba31d898ea1f179e206d1ad27ef`, Go pseudo-version `v1.8.1-0.20261023154812-2e00768cde3f`.
- `/usr/bin/go` was not the Go compiler (`Go: Unknown option: version`); no system binary was replaced.

## Exact build commands

Working directory: `/workspace/webhook-mcp-router/spike/mcp`.

```sh
GOTOOLCHAIN=local \
GOPATH=/workspace/webhook-mcp-router/.tools/gopath \
GOMODCACHE=/workspace/webhook-mcp-router/.tools/gomodcache \
GOCACHE=/workspace/webhook-mcp-router/.tools/gocache \
/workspace/webhook-mcp-router/.tools/go/bin/go get github.com/modelcontextprotocol/go-sdk@2e00768cde3f1ba31d898ea1f179e206d1ad27ef
```

Exit 0. Initial attempt without writable GOPATH failed because the checksum database path under `/home/agent/go` did not exist; corrected by explicitly selecting the project-owned GOPATH. Module verification remained enabled.

```sh
GOTOOLCHAIN=local \
GOPATH=/workspace/webhook-mcp-router/.tools/gopath \
GOMODCACHE=/workspace/webhook-mcp-router/.tools/gomodcache \
GOCACHE=/workspace/webhook-mcp-router/.tools/gocache \
/workspace/webhook-mcp-router/.tools/go/bin/go mod tidy
```

Exit 1. `github.com/segmentio/encoding@v0.5.4` redirected to `storage.googleapis.com`, which returned Forbidden. The signed URL query is redacted in `spike/mcp/logs/tidy.log`. No alternate dependency route or SDK patch was used to evade that failure. The prepared SDK test program and driver are **unexecuted scaffolding**, not successful SDK tests.

The independent standard-library probe compiled without that dependency:

```sh
GOTOOLCHAIN=local \
GOPATH=/workspace/webhook-mcp-router/.tools/gopath \
GOMODCACHE=/workspace/webhook-mcp-router/.tools/gomodcache \
GOCACHE=/workspace/webhook-mcp-router/.tools/gocache \
GOOS=wasip1 GOARCH=wasm \
/workspace/webhook-mcp-router/.tools/go/bin/go build -o probe.wasm ./probe
```

Exit 0. Native positive control used the same command without `GOOS`/`GOARCH`, output `probe-native`; exit 0. Source: `spike/mcp/probe/main.go`.

## Runtime commands and assertions

Full command arrays, stdout, stderr, and exit codes are in `spike/mcp/logs/*.json`.

```sh
WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer \
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
/workspace/webhook-mcp-router/spike/mcp/probe.wasm -- json
```

Input: `{"action":"opened","repository":"synthetic/demo"}`. Output preserved the object under `received`. Exit 0, empty stderr. See `logs/wasmer-json.json`.

```sh
python run-probes.py
```

Exit 0. This starts each listener, waits for its stdout ready marker, performs a host request to `http://127.0.0.1:18089`, and asserts native success versus Wasmer connection failure. The guest command includes `--net=ipv4:allow=127.0.0.1:18089/in`. The guest process exits normally after ten seconds; **its exit 0 does not mean HTTP was reachable**. See `logs/native-host-http.json` and `logs/wasmer-host-http.json`.

```sh
WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer \
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
/workspace/webhook-mcp-router/spike/mcp/probe.wasm -- exec
```

Exit 43, stdout `EXEC_RESULT: output="" error=pipe: Not implemented on wasip1`; stderr empty. See `logs/wasmer-exec.json`. A separate direct-stdio exec probe is recorded in `logs/wasmer-exec-direct.json` to separate pipe support from process support.

```sh
WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer \
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
--volume /workspace/webhook-mcp-router/spike/mcp/state:/state \
/workspace/webhook-mcp-router/spike/mcp/probe.wasm -- persist-write

WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer \
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
--volume /workspace/webhook-mcp-router/spike/mcp/state:/state \
/workspace/webhook-mcp-router/spike/mcp/probe.wasm -- persist-read
```

Separate instances, both exit 0. Exact persisted bytes asserted: `{"id":"sub_synthetic","mode":"dry_run"}`. See `logs/persist-write.json` and `logs/persist-read.json`. This is a filesystem capability test, not the requested MCP persistence flow.

## Source-grounded explanation

The downloaded Go toolchain's `src/net/net_fake.go` lines 5–8 describes fake networking for `js/wasm` and `wasip1/wasm`. Its `socket` function constructs `fakeNetFD`. `net.Listen` succeeding inside the guest therefore is not evidence that a host-reachable socket exists. The host request test is the decisive evidence here.

The cached official Go SDK provides `mcp.AddReceivingCustomMethod` (server.go:2367) and capability extension maps (protocol.go:2368), but top-level `events` serialization still requires a focused wire test. No SDK patch has been justified by an executed wire test in this spike.

The SDK's `mcp/streamable_server.go` documents `Stateless` mode (lines 113–123): each request has a temporary session, no session-ID validation, and no server-to-client requests. `JSONResponse` provides a single JSON POST response instead of SSE (lines 125–135). These can support investigating a simpler request/response control plane, but do not supply persistent application subscriptions or guarantee MCP host compatibility. Application state must survive separately.

## Smallest changes needed next

1. Resolve the SDK dependency download through an authorized functioning dependency supply path before running the prepared SDK tests. Current status is blocked by HTTP403, not a proven SDK/Wasm compile failure.
2. For genuine inbound HTTP from the host, use a verified WASIX-aware Go networking integration or a Wasmer host HTTP/preopened-socket adapter. Standard `net.Listen` plus `--net` did not suffice.
3. Historical diagnostic: stock Go `os/exec` failed in this target. The user has since stopped subprocess investigation and selected the in-process routing fork; no further process API work is planned. Embedding executable bytes would not add process syscalls.
4. Keep local Wasmer filesystem/network results distinct from Wasmer Edge configuration and durability. No Edge runtime was tested.

Direct exec follow-up: mounted an existing `router.wasm`, passed stdin/stdout/stderr directly (no capture pipes), and invoked `/state/router.wasm json`. Exit 43; stdout: `EXEC_DIRECT_RESULT: fork/exec /state/router.wasm: Not implemented on wasip1`. This isolates process startup failure from missing binary and capture-pipe issues.

## Follow-up: outbound HTTP versus raw TCP for storage access

Executed `python run-outbound.py` from `spike/mcp`; driver exit **0** means all expected positive/negative assertions passed. The driver compiled the same standard-library Go program natively and for `GOOS=wasip1 GOARCH=wasm`, each build exit 0. It started two host-local synthetic servers on dynamically allocated loopback ports, then exercised native controls and actual Wasmer guests. No database drivers, external services, credentials, or deployments were involved.

| Probe | Native control | Actual Go WASI guest in Wasmer 7.5.0 |
|---|---|---|
| HTTP GET to host loopback service | Exit 0; exact body `synthetic-host-http` | Exit 45; TCP connect refused before HTTP exchange |
| Raw TCP dial/write/read echo | Exit 0; exact echo `synthetic-host-tcp` | Exit 47; TCP connect refused |

Both guest runs had explicit, narrowly scoped permission: `--net=ipv4:allow=127.0.0.1:<port>/out`. Host request counters remained unchanged during each guest run; they increased during the native positive controls. This separates a healthy host endpoint from the Go WASI guest's fake-network behavior.

Actual commands in this run:

```sh
/workspace/webhook-mcp-router/spike/mcp/probe-native outbound-http 127.0.0.1:37533
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
  --net=ipv4:allow=127.0.0.1:37533/out \
  /workspace/webhook-mcp-router/spike/mcp/probe.wasm -- outbound-http 127.0.0.1:37533

/workspace/webhook-mcp-router/spike/mcp/probe-native outbound-tcp 127.0.0.1:47631
/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer run \
  --net=ipv4:allow=127.0.0.1:47631/out \
  /workspace/webhook-mcp-router/spike/mcp/probe.wasm -- outbound-tcp 127.0.0.1:47631
```

Environment: `WASMER_DIR=/workspace/webhook-mcp-router/.tools/wasmer`. Full build environments, commands, stdout, stderr, exit codes, request counters, and guest artifact hash are retained in `spike/mcp/logs/outbound-runtime.json`; rerunning the driver chooses fresh ports.

HTTP is an application protocol carried over TCP in this test; choosing an HTTP-based database API would not itself fix this stock-Go guest's socket integration. Conversely, this does **not** establish that Wasmer generally lacks outbound networking: a WASIX-aware runtime/guest or host HTTP adapter can have different behavior. Database driver compatibility, TLS, DNS, authentication, connection pooling, SQL protocols, transactions, and Wasmer Edge remain untested.
