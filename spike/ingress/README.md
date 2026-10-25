# Synthetic in-process ingress fork

Local source of `adnanh/webhook` pinned to `2bbdeb9f90b5f98c7b7b8976881efd6da9f69571`, with a focused patch in `inprocess.patch`. No external fork or publication was created. Original project licensing remains in `source/`.

**Uncompiled and untested.** Both native and WASI compilation are blocked by unavailable dependencies. See `../../docs/ingress-runtime-evidence.md`.

Only a configured hook named `synthetic-router` activates the new path. The handler intercepts that hook before the original parsing/execution code, requires POST, bounds raw bytes, verifies the fixed public synthetic HMAC key, then parses JSON. It does not invoke a subprocess or send any external requests. Existing hooks retain their upstream behavior.

`routeRegistry` copies policy sources and subscription ID membership on replacement and snapshots both once per request. All registered policies are evaluated independently with OPA's Go API, a restricted pure-builtin capability set, per-policy deadlines, and bounded decisions. Failed policies do not stop the next policy. Valid results contain only registered subscription IDs and a selected JSON `data` value. The only sink is a JSON dry-run response to the caller.

`source/synthetic-hooks.json` is a synthetic test configuration, not a deployment configuration. The shared signing key is deliberately public and must never be used for production. No management/auth endpoint or production routing mode is implemented.

The snapshot registry is process-local, not durable. CPU deadlines are cooperative; there is no hard evaluator memory sandbox. Payload-size checks apply after OPA evaluation, so this is not ready for untrusted policy authors. Runtime Wasmer networking must be solved independently. The existing Go/WASI probe's fake in-memory network does not establish external ingress support.

Storage direction: the receiver must use read-only policy/subscription access; MCP owns read-write registration. This patch's registry is only a synthetic in-memory snapshot stand-in. Its `replace` helper is used by tests, not exposed by the receiver. No database connection or registration-write endpoint exists. A future read-only database adapter and any separate delivery outbox must preserve that separation.

## Single-service MCP skeleton (uncompiled)

The same fork now optionally mounts `/mcp` when `-synthetic-router-mcp` is passed. It uses the official Go SDK pinned to `v1.8.1-0.20261023154812-2e00768cde3f`, `Stateless: true`, and `JSONResponse: true`; those APIs were checked against the cached SDK source. The route accepts only POST from a loopback peer with no Origin header and bounds request bodies. This is a local test guard, not production authentication.

Tools `synthetic_subscription_create` and `synthetic_subscription_list` mutate/read the same process-local registry that ingestion snapshots. Receiver evaluation accepts only `registrationReader`; MCP holds `registrationWriter`. That interface separation does not implement database roles or durability. Restart loses registrations.

`events/list` returns an illustrative event-definition envelope. `events/subscribe` and `events/unsubscribe` explicitly reject live lifecycle operations, directing callers to the synthetic tools. No callback challenge, signing, lease, replay, or live delivery exists. Top-level `capabilities.events` compatibility is still unresolved; this skeleton does not advertise a fabricated equivalent. No SSE path is required by this dry-run request/response flow; GET is rejected.
