# Webhook router requirements

Status: active synthetic POC implementation and runtime validation, updated 2026-10-25. Public repository: https://github.com/r33drichards/webhook-mcp-router. Publication and CI are authorized; the earlier ideation-only/no-push restrictions are withdrawn. One minimal free-tier Wasmer hosted E2E is authorized after real readiness checks. New hosted credentials, paid resources, production hooks/data and unrelated access changes remain unapproved.

The goal is one service that receives external webhooks, evaluates editable native OPA/Rego policies, and routes selected data to registered MCP webhook subscriptions. GitHub is the first provider. Tests use synthetic events only. No hosted deployment or hosted E2E success has occurred.

## Current evidence and limits

Actual CI run40160858958 on commit0430df942417eb3c43cb5a562aafb7cc93c080c3 passed the official SDK/native OPA fixture under Wasmer7.5.0 using pinned WASIX Go1.25.5: readonly dependency build, native tests, guest IP/TCP-DNS/TLS/cancellation/concurrency tests, fresh-instance state readback, event catalog/discovery, signed challenge, subscribe/renew/unsubscribe, signed synthetic ingress, native Rego routing and independent HTTPS signed callback receipt. No SDK source patch was required. See docs/runtime-evidence.md for logs and the deliberately retained unconfigured-client and UDP failure comparisons.

These are local Wasmer guest results, not Wasmer Edge results or complete upstream receiver feature parity. Shared database RO/RW enforcement, hosted DNS/persistence and Edge E2E remain unverified. Persistent mapped files are a synthetic fixture. Nix definitions are pinned but untested. Cloudscape/Monaco and production auth remain deferred.

The existing account WASMER_TOKEN is approved and saved. New isolated hosted service tokens/signing secret have not been created and need specific approval. docs/hosted-next-gate.md lists their destinations, scope and proposed lifetime. No paid resources or production events are authorized.

## Confirmed user requirements

- Create a separate project/repository rather than modifying the existing MCP project.
- Make a local fork/patch of the Go webhook receiver (`adnanh/webhook` is the inspected candidate), integrating routing business logic in-process after request verification. The former subprocess/CLI handoff design is superseded.
- Use OPA’s native Go API evaluator in the combined ingress program as the primary approach. For each verified incoming request, snapshot all registered policies, evaluate each policy against that request, and use each result to select registered subscription IDs and the information/payload to forward. The separate CLI is no longer required.
- Provide editable routing/filtering policies, including an MCP tool for managing them.
- Consolidate into ONE Go service embedding the webhook receiver fork, OPA native Go evaluator, and official Go MCP SDK HTTP routes. This supersedes the separate-service/language-flexible exploration. Patch the SDK only if a verified event-extension gap requires it. Follow the actual WeeChat MCP event convention rather than inventing a generic MCP standard.
- Support OpenAI-style MCP event subscription WEBHOOK delivery using the verified WeeChat convention. Subscriptions and webhook callbacks must not require a persistent client connection; do not substitute SSE or describe the extension as universal core MCP.
- Aim to run the entire POC in Wasmer if feasible, including the in-process ingress/evaluator and MCP control plane. Investigate the specific runtime/hosting mode; feasibility is not established. Keep native execution only as a comparison or fallback to discuss, not the chosen architecture.
- Use a shared durable database for policy and subscription registration. The webhook receiver must connect with read-only permissions; the MCP control plane must connect with read-write permissions. Delivery/outbox state is separate and must not silently expand receiver access to the registration database.
- Use Nix as the build system for reproducible, pinned builds and explicit patches where needed.
- Provide a basic admin UI using Cloudscape Design and a Monaco editor for Rego.
- Focus on the minimal POC first. Dex/Pomerium and native MCP authentication are alternatives to revisit later; neither authentication architecture nor a standalone GitHub application is required for this POC.
- Keep the project POC-focused. The initial ideation pause was superseded by explicit authorization for a synthetic local Wasmer feasibility spike, including a local in-process ingress fallback if needed. No UI implementation until runtime boundaries are resolved.

Project name and public visibility are decided: webhook-mcp-router under r33drichards. Hosting target is Wasmer if verified feasible. No production credentials, real webhook registrations or real event forwarding are authorized. Minimal synthetic hosted deployment remains gated by runtime, app-secret and free-allowance checks.

## Minimal POC scope

Current acceptance criteria for the authorized synthetic spike:

1. Patch a local Go webhook checkout so a verified request invokes routing logic in-process. No subprocess is required. Preserve original raw-body signature verification; verify before parsing/evaluating the routing input.
2. Snapshot the registered policy set/version once per request and evaluate **every** policy independently through OPA's native Go API. A malformed, failing, or timed-out policy must not prevent evaluation of other policies. Bound policy count, source size, input, evaluation time, and result size; disable policy network access.
3. Each policy returns registered subscription IDs and bounded information/payload for those subscriptions. Validate IDs against the registry and reject arbitrary URLs. Use synthetic policies, subscriptions, and a recording sink only. Define collision/dedup behavior when multiple policies select one subscription.
4. Execute matching, nonmatching, policy-failure, and multiple-policy cases in the actual Wasmer target. A native-only pass is insufficient. Compiled OPA policy Wasm is a fallback whose separate success does not satisfy the embedded evaluator requirement.
5. Test the same Go service’s stateless MCP HTTP control routes under local Wasmer: initialize over a supported HTTP transport, create a synthetic subscription through a tool, then read it after a fresh instance using suitable local storage. Distinguish local results from Wasmer Edge viability.
6. Keep Nix as the desired reproducible build/patch system. No UI implementation until ingress/evaluator/runtime boundaries are resolved. Cloudscape/Monaco remains the intended later admin interface.

```text
Verified synthetic webhook -> local patched Go ingress
  -> snapshot registered policies -> OPA Go API evaluates each policy
  -> validate subscription IDs + bounded selected payload -> recording sink

ONE Go service:
  MCP HTTP control routes -- read-write handle --> registration/policy DB
  Webhook ingestion -- read-only handle --> same registration/policy DB
Delivery/outbox state: separate authority and lifecycle
Later: Cloudscape/Monaco policy editor and sample/route preview
```

The entire POC should run in Wasmer if feasible. Authentication dependencies remain minimal; Dex/Pomerium and production identity/deployment architecture are deferred. Full reliable delivery, queueing, and production authorization are not claimed by this synthetic spike.

## Executed Wasmer checkpoint

Actual local runtime evidence is recorded in [docs/runtime-evidence.md](docs/runtime-evidence.md), with reproducible commands, inputs, versions, logs, exit codes, and assertions. This supersedes earlier docs-only feasibility notes.

| Stage | Actual result | What it establishes |
| --- | --- | --- |
| OPA 1.9.0 compiled policy in Wasmer 7.5.0 | PASS: matching input selects exactly `sub_match`; nonmatch selects none; malformed JSON rejected | Policy runs as a Wasm guest in a native C host using Wasmer's official library; not a Go guest or Edge proof |
| Go 1.27.3 stdlib WASI JSON probe | PASS | A simple Go guest runs locally |
| Go WASI HTTP self-loopback | PASS, but uses Go's in-memory fake network | Not externally reachable HTTP |
| Host request to Go WASI loopback listener | FAIL: connection refused; native equivalent HTTP 200 | Tested standard Go/WASI path does not expose a real host-reachable listener |
| Go WASI subprocess (superseded design) | FAIL: `pipe: Not implemented on wasip1`, exit 43 | Unchanged ingress → packaged CLI subprocess chain is blocked |
| Go WASI outbound HTTP / TCP | FAIL: exits 45 / 47, connection refused; native controls pass | Neither service reached; no database connectivity established |
| Fresh-process subscription file readback | PASS through explicit local mapped directory | Local storage only; not MCP or Edge persistence |
| Embedded Go Rego / official Go SDK builds | BLOCKED by dependency download HTTP 403 | No result on their Wasmer runtime compatibility |
| Nix build | NOT RUN: Nix and `/nix` absent | Pinned definition prepared, not validated/built |

The subprocess experiment is now stopped and retained only as historical diagnostics. The user explicitly selected an in-process local Go ingress fork/patch with OPA’s Go evaluator. Real HTTP and embedded Go/OPA integration remain unproven. A concrete combined-service patch is prepared in `spike/ingress/inprocess.patch`; native and WASI build attempts failed at missing dependencies. Its runtime status is separate from the compiled-policy fallback result.

The next useful step is to establish an authorized dependency source and a supported real HTTP integration for the selected Wasmer mode, then execute the Go in-process fallback. Serverless MCP acceptance remains: initialize over supported HTTP, create a synthetic subscription through a tool, restart into a fresh instance, and read it back. That end-to-end test did not run; local file persistence is separate evidence.

## Verified WeeChat MCP convention

Inspected through the authorized GitHub connector at commit `7d934730d6b6864a937035201f6caa039b080792`.

- Custom methods are `events/list`, `events/subscribe`, and `events/unsubscribe`; discovery advertises an `events` capability. The source calls this a draft Events capability, so it should not be presented as universal MCP support. [Protocol adapter](https://github.com/r33drichards/weechat-mcp/blob/7d934730d6b6864a937035201f6caa039b080792/event_protocol.py)
- Subscribe accepts `name`, `arguments`, `delivery: {mode: "webhook", url, secret}`, and optional `cursor`/`ttlMs`. Unsubscribe identifies the same name, arguments, and delivery URL, without a secret. The authenticated principal comes from trusted server context.
- Subscription identity includes owner, callback URL, event name, and canonical arguments. Subscribe returns `id`, `refreshBefore`, `cursor`, and `truncated`. Callback activation uses a signed `{type: "verification", challenge}` exchange. [Subscription manager](https://github.com/r33drichards/weechat-mcp/blob/7d934730d6b6864a937035201f6caa039b080792/mcp_events.py)
- Event deliveries contain `eventId`, `name`, `timestamp`, `data`, and `cursor`. Standard Webhooks signing uses `webhook-id`, `webhook-timestamp`, `webhook-signature`, plus `X-MCP-Subscription-Id`. [Signing implementation](https://github.com/r33drichards/weechat-mcp/blob/7d934730d6b6864a937035201f6caa039b080792/event_webhooks.py)

Reuse the subscription and delivery convention, not WeeChat's IRC-specific `message.created` data schema. The router's event names, arguments, and payload schemas remain to be chosen. Host-created subscriptions supply destinations; a Rego editor must not fabricate chat callbacks. [WeeChat event workflow](https://github.com/r33drichards/weechat-mcp/blob/7d934730d6b6864a937035201f6caa039b080792/MCP_EVENTS.md)

## Go ingress source findings (subprocess design superseded)

`adnanh/webhook` is the inspected source for the local in-process patch. The command/file handoff findings below explain the earlier design; they are no longer required implementation work. The current patch replaces command launch with the routing evaluator.

For GitHub, configure a required `payload-hmac-sha256` trigger rule using `X-Hub-Signature-256` and the configured source secret. Verification is not automatic: a hook without a trigger rule executes without this check. Other providers require their own authentication rules or adapters; a generic HMAC rule does not cover every provider's signing format. [Rules](https://github.com/adnanh/webhook/blob/2bbdeb9f90b5f98c7b7b8976881efd6da9f69571/docs/Hook-Rules.md), [GitHub signature guidance](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

Source inspection reveals integration details that need a deliberate choice:

- `raw-request-body` preserves the request bytes; `entire-payload` serializes the parsed payload again. Do not use the latter to reconstruct signed bytes.
- `pass-file-to-command` can provide a body file path through an environment variable. Selected headers can be passed separately. Prefer this over putting large or sensitive JSON in argv. A small fixed wrapper can construct the desired JSON envelope and feed CLI stdin.
- The inspected command runner does not assign stdin. Direct JSON-on-stdin therefore needs that wrapper or a receiver change.
- The handler parses JSON before evaluating signature trigger rules. Strict verification-before-parsing requires a small patch or a carefully reviewed raw-body mode that defers JSON parsing to the authenticated CLI path.
- By default the command is launched asynchronously and the HTTP response does not wait for durable storage. Synchronous capture mode waits for exit but exposes command output; use only fixed sanitized output if adopting it. Command execution lacks an explicit deadline in the inspected path.

These findings come from [request value extraction](https://github.com/adnanh/webhook/blob/2bbdeb9f90b5f98c7b7b8976881efd6da9f69571/internal/hook/hook.go#L440) and [request handling/command execution](https://github.com/adnanh/webhook/blob/2bbdeb9f90b5f98c7b7b8976881efd6da9f69571/webhook.go#L382). A bounded proxy or receiver changes would also be needed for request limits; the inspected handler reads the body with `ReadAll`. Verbose execution logs include arguments, environment additions, and command output, which strengthens the case for file handoff and sanitized logging.

## Wasmer and serverless investigation

OPA compiles a selected Rego decision to Wasm. That produces a policy module, not an OPA server or a standalone stdin CLI. A host must implement OPA's ABI, memory/input/output handling, and required imports. Some built-ins need host implementations. Restrict the policy capability set and expose no network built-ins. [OPA Wasm documentation](https://www.openpolicyagent.org/docs/wasm).

Wasmer can host Wasm, but the complete pipeline is not automatically portable. Its documentation states that Go's `wasip1` target lacks the WASIX sockets/subprocess model. Therefore, do not assume ordinary Go cross-compilation makes the existing ingress, HTTP server, or process-launch chain work unchanged. Investigate compatible host adapters or runtime-specific integrations while preserving the all-in-Wasmer goal. The executed spike below documents the tested standard-Go runtime boundaries; a supported end-to-end alternative is still required. [Wasmer WASIX guidance](https://docs.wasmer.io/runtime/wasix/).

A serverless control plane can keep request handling stateless while storing subscriptions, policy versions, secrets, receipts, and queues externally. Wasmer persistent volumes exist, but the current documentation warns that read-write-many volumes under autoscaling are not well suited to single-writer databases. Do not assume a shared SQLite file provides safe serverless state. Prefer a transactional database and durable queue/worker design; providers are undecided. [Wasmer volume semantics](https://docs.wasmer.io/edge/learn/volumes/).

## Stateless MCP control versus webhook delivery

The combined service should handle MCP control requests without a long-lived client connection. The inspected official SDK exposes `Stateless` mode (temporary sessions per request, no session-ID validation or server-to-client requests) and `JSONResponse` (single JSON POST responses rather than SSE). These are candidate transport settings, not proof of host interoperability. Durable subscriptions belong in application storage and survive request sessions; webhook delivery is an independent outbound operation.

`events/list`, `events/subscribe`, and `events/unsubscribe` remain the verified extension methods below. Host-supplied callback URLs/secrets, signed verification challenges, and subsequent signed webhook envelopes must follow that convention. Do not treat ordinary resource subscriptions or SSE notifications as replacements. Exact discovery and subscription wire compatibility still needs execution once dependency and HTTP runtime blockers are resolved. [SDK HTTP options](https://github.com/modelcontextprotocol/go-sdk/blob/2e00768cde3f1ba31d898ea1f179e206d1ad27ef/mcp/streamable_server.go).

## Go SDK integration: verified source and conditional patching

Inspected official `modelcontextprotocol/go-sdk` source at commit `2e00768cde3f1ba31d898ea1f179e206d1ad27ef`. This is a research reference, not yet the project's selected dependency pin.

- `mcp.AddReceivingCustomMethod` registers typed custom JSON-RPC methods and sends them through the normal middleware chain. Use it as the first candidate for `events/list`, `events/subscribe`, and `events/unsubscribe`; do not assume custom dispatch requires a fork. [Registration API](https://github.com/modelcontextprotocol/go-sdk/blob/2e00768cde3f1ba31d898ea1f179e206d1ad27ef/mcp/server.go#L2367).
- `ServerCapabilities` has `experimental` and `extensions` maps, but no top-level `events` field in the inspected definition. These map keys are not automatically wire-equivalent to WeeChat's `capabilities.events`. Confirm host discovery expectations and serialization with a focused wire test. Only then choose an adapter or small patch for the actual mismatch. [Capabilities](https://github.com/modelcontextprotocol/go-sdk/blob/2e00768cde3f1ba31d898ea1f179e206d1ad27ef/mcp/protocol.go#L2368).
- Resource subscription handlers are not the webhook event subscription protocol. Event schemas, callback verification, signing, expiry, and delivery state remain application responsibilities.
- `auth.RequireBearerToken` accepts an application-supplied `TokenVerifier`, checks expiration/scopes, and attaches `TokenInfo` to context. `ProtectedResourceMetadataHandler` serves discovery metadata. The verifier must establish token validity and intended resource/issuer as appropriate; middleware is not a token issuer. [Auth components](https://github.com/modelcontextprotocol/go-sdk/blob/2e00768cde3f1ba31d898ea1f179e206d1ad27ef/auth/auth.go).
- The SDK's auth server example explicitly expects a separate authorization server and introspection endpoint. Thus using the SDK's auth support does not itself provide a production authorization server, login, consent, credential lifecycle, or refresh service. A lightweight POC auth boundary can avoid Dex/Pomerium, but must not be described as complete MCP OAuth merely because it checks a bearer token. [Server auth example](https://github.com/modelcontextprotocol/go-sdk/blob/2e00768cde3f1ba31d898ea1f179e206d1ad27ef/examples/auth/server/main.go).

The initial local SDK build was blocked by dependency HTTP 403. The permitted GitHub CI path subsequently compiled the SDK/native-OPA fixture and passed native custom-dispatch, discovery, lifecycle and redaction tests. Middleware exposes the top-level event capability without a source patch. Guest and hosted wire tests remain separate gates. Any future SDK patch must remain narrow and versioned.

## Nix build requirement

Use Nix to pin the Go toolchain, SDK source, OPA/compiler, Wasmer/runtime tools, ingress source, and UI dependencies. Preserve Go module and UI lockfiles. Record any patches as explicit build inputs with upstream revision and purpose; apply them during the build rather than editing an installed SDK. Nixpkgs provides a patch phase and Go build helpers. This establishes a reproducible build plan; reproducibility still needs verification for the selected toolchains and targets. Nix does not add missing runtime syscalls or make a Wasm target compatible by itself. [Nixpkgs manual](https://nixos.org/manual/nixpkgs/stable/).

The subsequent authorized spike prepared a pinned Nix build/patch definition. Nix is absent, so it was not evaluated or built. Runtime tests executed outside Nix are identified separately.

## Distinguishing Wasmer runtime options

- **Standard Go WASI:** `GOOS=wasip1 GOARCH=wasm` targets WASI preview 1. Stdin/stdout and suitable filesystem operations make a pure JSON-processing CLI a promising first test. Standard Go does not automatically gain full socket creation or subprocess execution from running on Wasmer. Goroutines are not proof of OS-thread/process support. [Go WASI documentation](https://go.dev/blog/wasi).
- **WASIX-capable host:** Wasmer's WASIX provides additional sockets, threads, fork/exec, and pipes for compatible guests. A standard Go WASI binary does not automatically use these extensions. Go host-import adapters or other integrations require version-specific investigation and tests. This is a Go guest/toolchain limitation, not a claim that Wasmer cannot network or spawn processes. [Wasmer WASIX documentation](https://docs.wasmer.io/runtime/wasix/).
- **Local Wasmer versus Wasmer Edge:** a local Wasmer embedding can supply custom host imports and orchestration. That does not establish that the same imports, subprocess layout, HTTP transport, persistence, or worker lifecycle are available in the intended Edge mode. Select and test the hosting mode explicitly. Do not infer all-in-Edge support from one local policy evaluation.
- **OPA inside a Go Wasm guest:** native embedding of OPA in Go and hosting an OPA-compiled Wasm policy are different approaches. The former needs a Go/WASI build-and-evaluation test; the latter needs an OPA ABI host and a viable way to compose it with the Go guest. The compiled-policy approach passed using a native C Wasmer host; the embedded-Go approach was blocked before compilation. Nested Wasm/runtime support inside the Go guest was not tested.

Remaining staged validation plan: Nix-pinned Go stdin/stdout module in local Wasmer; one pure Rego decision using the chosen evaluation approach; official SDK custom events over an in-memory/stdio transport; then the selected HTTP/ingress/process handoff mode. Keep each result separate. Only the final transport/process tests can establish the complete POC's viability in the chosen Wasmer deployment mode.

## Shared registration and policy storage

Confirmed: both code paths in the one Go service use the same durable registration/policy database. The webhook receiver has a **read-only connection/identity**; the MCP control plane has a **read-write connection/identity**. Use separate credentials/roles and enforce grants at the database or authenticated data gateway. Also narrow the Go interfaces exposed to each code path. This is logical least-privilege separation, not full credential/process isolation: a compromised combined process can potentially access both handles. Stronger isolation would require a later architecture change, not an implicit claim. Keep delivery receipts, retries, deduplication, and outbox state in a separate store/authority; do not give the receiver registration-write permission to simplify delivery bookkeeping.

Choose storage only after checking actual runtime support. Compare HTTP-accessible database gateways with scoped credentials, PostgreSQL over TCP/TLS with distinct roles, and local SQLite as a limited single-host prototype. Actual local tests now show both HTTP and raw TCP outbound calls fail from the tested stock-Go WASI guest, while native controls pass; an HTTP database does not solve that networking boundary. An HTTP database still needs a working outbound network transport; local mapped-file persistence does not establish safe shared/serverless SQLite. Assess cold starts, connection pooling, query/transaction semantics, request-level policy snapshots, and consistency immediately after MCP policy activation. Pin/cache policies by version with explicit freshness behavior. Supply credentials separately by least-privilege service identity; do not place them in Rego, payloads, or logs.

The sourced comparison is in [docs/storage-options.md](docs/storage-options.md); actual outbound logs are in `spike/mcp/logs/outbound-runtime.json`. No database driver, TLS session, or remote database connection has been tested. No external database provisioning, paid service selection, credentials, or access configuration is authorized in this spike. Synthetic local connection tests and a sourced comparison are permitted; storage selection remains open.

## Deferred production notes: authentication and deployment isolation

Robert proposed Dex/Pomerium and later raised native MCP authentication as an alternative. The production stack decision is deferred. Prefer minimal auth dependencies for the POC, and investigate lightweight SDK integration only to the extent needed for its local boundary; do not build a production identity system now. One possible future browser flow is: GitHub login → Dex as OIDC issuer → Pomerium as authenticated proxy → admin UI/control plane. MCP client authentication still needs a separate compatibility review; an interactive browser session alone does not establish a working MCP OAuth flow. Provider webhook ingress must use provider-specific request authentication rather than an interactive login redirect.

Dex documents a GitHub OAuth2 login connector with client ID, client secret, and callback at `(Dex issuer)/callback`. This supports investigating a dedicated GitHub **OAuth App** for login. It does not establish that a GitHub **App** installation is required for authentication. Pomerium supports generic OIDC configuration, which makes Dex a plausible upstream issuer; the complete configuration remains untested. [Dex GitHub connector](https://dexidp.io/docs/connectors/github/), [Pomerium generic OIDC guidance](https://www.pomerium.com/docs/integrations/user-identity/oidc).

Separately, a GitHub **App** may be useful as the webhook source, with selected repository installations, granular permissions, and event subscriptions. Login identity permissions and repository/webhook permissions serve different purposes. Do not grant repository write permissions merely to sign in. Confirm whether the initial source is a manually configured repository webhook or a GitHub App, and whether one or two dedicated registrations are appropriate. GitHub Apps can also support user OAuth flows; that alone does not prove compatibility with the chosen Dex connector. [GitHub App versus OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/differences-between-github-apps-and-oauth-apps).

Deferred questions and regression coverage:

- Choose a stable issuer and exact callback URLs for each leg: GitHub → Dex and Dex → Pomerium. Define MCP client redirect URIs and audiences separately.
- Decide independent deployments/stores versus shared issuer infrastructure, and whether GitHub applications should be per deployment; isolate this project's client registrations, session/cookie scope, signing/encryption keys, storage, and environment configuration from unrelated services.
- Derive owner identity from verified claims, not user-controlled headers. Decide claim-to-role mapping for readers, policy editors, subscription owners, and administrators.
- Verify refresh behavior under concurrent browser/API/MCP requests, multiple replicas, token rotation, process restart, and logout/revocation. Test races so one refresh cannot overwrite a newer token or cross client/session boundaries. Dex's connector re-queries GitHub during refresh, so its datastore and upstream availability matter.
- Validate the eventual authentication flow with synthetic/local tests before live changes. No production app registration, new credentials or live authentication configuration is authorized; the separately approved synthetic hosted POC remains subject to its readiness gates.

## Deferred admin workflow

Use Cloudscape for navigation, forms, tables, status, and dialogs; embed Monaco for Rego editing. Treat Monaco integration and Rego diagnostics as explicit work rather than assuming an existing Cloudscape component provides them. [Cloudscape components](https://cloudscape.design/components/), [Monaco](https://github.com/microsoft/monaco-editor).

For the POC, use one policy/editor/sample/preview page. Sources, event definitions, subscriptions, and delivery history pages can follow later. Policy editing should follow **draft → validate → evaluate sample event → preview selected subscription IDs → activate version**. Show compilation errors, matched destinations by safe labels, exclusions, and the policy version. Use synthetic/redacted samples. Preview must perform no callback sends. Local draft selection is enough for the POC. Production activation, rollback, authorization, and audit are deferred.

## Unresolved choices (POC first, production later)

1. Validate the local ingress patch and signature-before-parse behavior in the actual Wasmer runtime; select a supported HTTP integration if standard Go WASI is insufficient.
2. Define the in-process request/policy-result contract: trusted source metadata, policy snapshot/version, selected payload shape, limits, and handling overlapping policy selections.
3. Choose generic versus provider-specific event names, subscription arguments, payload schemas, and whether payload transformations belong in scope.
4. Primary: embedded OPA Go API. Resolve dependency access and validate it under Wasmer. Consider compiled policy Wasm only as a documented fallback if necessary.
5. Deferred: choose principal/tenant model, source ownership, policy-edit permissions, callback secret storage and rotation.
6. Deferred: choose database, queue, worker lifecycle, retry limits, dedup/replay retention, ordering, and backpressure behavior.
7. Deferred: define policy activation semantics for events already queued, and refresh/unsubscribe/expiry behavior across workers.
8. Project/repository/public visibility are settled. License selection, production hosting and operating model remain unresolved.

## Current work state

The separate public repository contains the Go receiver fork spike, an official-SDK/native-OPA CGI fixture, source references, runtime logs and pinned-but-untested Nix definitions. The fixture now implements exact event method names, discovery capability, signed callback verification, owner-scoped persisted grants, TTL checks and policy routing. Native tests and Wasm compilation passed in CI. Guest DNS/TLS/concurrency/lifecycle checks subsequently passed in run40160858958. Earlier local dependency denials were not bypassed. The original full receiver fork and this focused hosted fixture remain distinct probes; fixture success does not establish complete upstream webhook feature parity. No managed Edge deployment or production integration has occurred, and the preloaded MCP project remains unchanged.

## Deferred production delivery safeguards

Before real delivery, design durable receipts/outbox acknowledgement, retries, replay retention, expiry, unsubscribe handling, and dead-letter processing outside OPA. Define at-least-once semantics and stable IDs. GitHub body signatures do not prove freshness or authenticate event/delivery headers.

Verify callbacks by signed challenge; enforce HTTPS, public-address checks, DNS revalidation/address pinning, TLS verification, no redirects, and bounded responses. Keep secrets out of policy inputs and logs. Apply owner/scope checks independently of Rego, and version policy activation. These are future production requirements to review, not extra work for the minimal dry-run POC.
