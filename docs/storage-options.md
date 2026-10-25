# Shared storage options

Status: design comparison, 2026-10-25. No database provisioned, credentials created, or access changed.

**Confirmed boundary:** one Go service embeds ingress, OPA, and MCP routes. It uses one shared durable policy/registration database, with a **read-only ingestion handle/identity** and a **read-write MCP control handle/identity**. Never grant registration writes to ingestion for retries. Separate database roles enforce each connection's permissions, but credentials co-resident in one process provide logical separation, not a complete compromise-isolation boundary.

## Recommendation

Investigate a narrow HTTPS database API backed by transactional PostgreSQL first. This moves connection pooling into the gateway and can enforce database permissions. **It is not a networking workaround:** actual outbound HTTP and TCP probes both failed in the stock Go WASI guest. Resolve socket integration before selecting either remote option.

| Option | Advantages | Limits and access enforcement |
| --- | --- | --- |
| HTTPS API, e.g. PostgREST over PostgreSQL | Request-oriented interface; gateway owns database pooling; suitable for short-lived clients. | Distinct signed identities map to database roles. Receiver gets SELECT on sanitized routing views only; MCP gets scoped CRUD or controlled mutation functions. An HTTP GET-only convention is insufficient if its token can also write. Deny mutating RPCs and privileged role switching. |
| PostgreSQL over TCP/TLS | Direct transactions, constraints, snapshot isolation, and database roles; fewer API components. | Requires a working guest TCP/DNS/TLS integration and compatible driver. Small bounded pools or a pooler are needed to avoid connection multiplication during cold starts. Receiver role gets SELECT; MCP's role gets only required writes, never owner/superuser authority. |
| Local SQLite | Small local synthetic POC; no network dependency. | File ownership/mount permissions enforce separation, not separate SQL login roles. A read-only connection flag alone is not an isolation boundary when the process can rewrite the file. Suitable for a controlled single-host arrangement, not assumed safe across autoscaled Edge replicas. |

[PostgREST role mapping](https://docs.postgrest.org/en/v13/references/auth.html) and [PostgreSQL privileges](https://www.postgresql.org/docs/current/sql-grant.html) support enforceable identity separation. Audit inherited/PUBLIC grants and exposed functions, not only table grants.

## Runtime boundary

Actual Go **1.27.3** / local Wasmer **7.5.0** probes: native HTTP GET and raw TCP echo passed (exit 0). Stock Go WASI outbound HTTP failed (exit **45**) and TCP failed (exit **47**), both with connection refused despite exact loopback `--net=ipv4:allow=127.0.0.1:<port>/out` grants. Host request counters did not increase after either guest attempt. [Exact commands, outputs, and assertions](../spike/mcp/logs/outbound-runtime.json).

The earlier in-guest HTTP self-loopback pass used Go's fake network, not an OS socket. No external database, HTTPS/TLS connection, or Wasmer Edge deployment was tested. WASIX offers additional network capabilities; stock Go WASI does not automatically use them. A verified guest socket/HTTP adapter is the next prerequisite. [Go WASI limits](https://go.dev/blog/wasi), [Wasmer WASIX](https://docs.wasmer.io/runtime/wasix/).

## Consistency and delivery state

Return the active policy hash/version and eligible registrations as one consistent snapshot—one query or appropriately isolated transaction, not unrelated HTTP reads. Activate versions atomically; use compare-and-swap for edits. Cache immutable versions with bounded freshness, recording the snapshot used for each decision. Recheck revocation/expiry before actual delivery. PostgREST requests are transactional, but separate requests are not one snapshot. [Transaction semantics](https://docs.postgrest.org/en/v13/references/transactions.html).

Exclude signing secrets from receiver-readable views unless a later explicit requirement needs them; policies receive neither credentials nor callback secrets. Keep intake/outbox append/dedup and delivery retry/ack permissions separate from registration writes, even when implemented as modules in this one service. The receiver's policy/registration identity stays read-only. Durable acceptance/queueing and transaction boundaries remain unresolved.

Wasmer documents read-write-many regional volumes as unsuitable for single-writer database assumptions under autoscaling. SQLite WAL requires same-host shared memory; local persistence alone proves neither database locking nor Edge durability. [Wasmer volumes](https://docs.wasmer.io/edge/learn/volumes/), [SQLite WAL](https://www.sqlite.org/wal.html).
