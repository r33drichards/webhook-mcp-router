# C# isolated Functions on Windows Consumption

Current user decision: C#, classic Consumption, alerts approaching the free allowance. Azure SQL remains selected. Billing upgrade, subscription/region, budget and notification recipient are unresolved with the parent. No Azure resources, identities, credentials, roles, firewall rules, billing settings or alerts have been changed.

## Verified support and pins

Use Functions runtime4, Windows classic Consumption (Y1), .NET10 isolated worker. Microsoft documents .NET10 support for isolated Functions and excludes .NET10 specifically on Linux Consumption. Do not use the in-process model, whose support ends November10,2026. Do not accidentally provision Flex, whose free grant differs.

Pinned SDK10.0.402 was obtained from official release metadata; Linux archive SHA5121904a98dda2db34ba78ba3c4fb1b224455329af91c341d83547843c1839e112b04ae699ee92fa2449a8f62249196a938723078c0c60b9f65c88539d5687729c2. `dotnet --version` passed. Actual cloud runtime availability still requires subscription/region validation.

NuGet pins match the inspected Microsoft sample project: Worker2.52.0, Worker.Sdk2.0.7, Http.AspNetCore2.1.0, MCP extension1.5.0. These are fixed direct dependencies; a restored transitive lockfile is still needed before claiming reproducible release builds. Nix remains desirable for build orchestration, while Windows execution needs a Windows runner.

Sources:
- https://learn.microsoft.com/en-us/azure/azure-functions/dotnet-isolated-process-guide
- https://github.com/Azure-Samples/remote-mcp-functions-dotnet/blob/main/src/FunctionsMcpTool/FunctionsMcpTool.csproj (inspected blob6226c9b22145e080bee9d0ae39e7cba04b039c42)
- https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-mcp

## MCP and event semantics

Use the Functions MCP extension for tools, Streamable HTTP endpoint /runtime/webhooks/mcp, with default system-key authorization retained. No unauthenticated management endpoint is enabled. OAuth/client integration remains a separate decision; a system key is not OAuth. The local Functions scaffold exposes only router_status and truthfully reports incomplete persistence/event support. No successful subscription creation is fabricated.

Implement policy validation, sample evaluation, policy activation and subscription management tools on shared domain services backed by SQL. Existing WeeChat event wire behavior remains the contract: event catalog/discovery, signed verification challenge, subscription identity/expiry, renew/unsubscribe and signed callback envelope. MCP tool support alone does not implement the events/* extension. The Functions MCP extension's custom-method integration point is not yet verified; it is a readiness blocker, not permission to replace events/* with SSE or approximate tool-only semantics. Inspect the extension's C# SDK hooks before deciding whether a narrowly scoped extension/HTTP dispatcher is required.

## Rego evaluator decision

Primary candidate: package official OPA1.9.0 Windows amd64 executable and invoke opa eval from C# through ProcessStartInfo.ArgumentList with shell execution disabled. This runs OPA's native evaluator in a process, preserving Rego semantics; it is not a native C# interpreter and not the former embedded Go API.

Verified release artifact: https://github.com/open-policy-agent/opa/releases/download/v1.9.0/opa_windows_amd64.exe
SHA256ea07eb413f7d0b258dc2e45d054ebb7df6fad42ad436bbe96e5dc6d5e7bc2951.

Local implementation bounds source/input/output, passes JSON on stdin, uses unique temporary policy files, clears inherited environment secrets, restricts builtins using the existing capabilities file with allow_net empty, fixes the query to data.router.routes, uses an OPA evaluation timeout plus an outer process deadline/kill, and validates returned subscription IDs against an explicit eligible set. No arbitrary policy URL or command is accepted. The preview payload contract uses subscription_id and payload; migration from the earlier fixture's data field is still required and must be explicit.

Remaining process risks: Windows Functions sandbox child-process allowance, process startup/memory billed to Consumption, cancellation and concurrent load under actual hosting, and per-policy memory limits. Output and time limits are not a hard child-process memory cap. Do not claim complete sandboxing. Test malformed/nonmatching/matching policies, no-network builtins, cancellation, file isolation and registered-ID restrictions under Windows CI, then the real Functions host.

Alternatives:
1. A small packaged Go evaluator CLI using the existing Go OPA API can retain an almost identical business interface, but adds another binary build/toolchain. It has the same host subprocess risk.
2. Compile policies with official OPA to Wasm and use a .NET host. OPA lists community .NET integrations; this is not an official built-in .NET Rego evaluator. Vet ABI/builtin support, Windows native runtime, fuel/memory limits and maintenance before selection. Policy edits require compilation before activation.
3. A separately hosted OPA REST service preserves official semantics but adds credentials, latency, availability and paid infrastructure. Not authorized or provisioned.

Sources: https://openpolicyagent.org/docs/cli ; https://openpolicyagent.org/docs/wasm ; https://openpolicyagent.org/ecosystem/entry/opa-wasm-dotnet .

## Durable state and permissions

SQL stores versioned policies and subscription metadata. Ingestion obtains a consistent snapshot using a read-only registration principal. MCP control has read-write registration permissions. Outbox writes use separate narrowly scoped authority, never grant receiver registration writes to accommodate retries. If all handlers share one process/identity with all grants, separation is logical only; separate Function apps/identities are recommended for enforceable isolation, pending approved role configuration.

Persist validated selected deliveries and dedup identity before successful ingress acknowledgment. A dispatcher publishes outbox rows to a storage queue; a queue-triggered worker delivers signed callbacks with retry/poison handling. Use durable leases/unique constraints for concurrent invocations, at-least-once delivery and idempotent recipients. Do not promise exactly-once callback receipt. SQL polling/change-tracking cadence must account for waking a free serverless SQL database and exhausting its allowance. SQL storage adapter, transactional outbox, dispatcher and worker remain unimplemented in this C# scaffold.

## Alerts: precise allowance thresholds

Classic Consumption eligible subscription-wide monthly allowance:1,000,000 executions and400,000GB-seconds. Aggregate all eligible classic Consumption apps, not only this app. Do not substitute Flex metrics or grants.

| Threshold | FunctionExecutionCount | GB-seconds | FunctionExecutionUnits (MB-ms) |
|---|---:|---:|---:|
|80%|800,000|320,000|327,680,000,000|
|90%|900,000|360,000|368,640,000,000|
|100%|1,000,000|400,000|409,600,000,000|

Conversion: FunctionExecutionUnits /1,024,000 = GB-seconds. Read Total aggregation from calendar-month start through now (UTC), not sampled Application Insights request counts. A rolling24-hour metric alert is not a month-to-date budget alarm. Proposed hourly collector queries Azure Monitor and persists emitted thresholds per subscription/month/meter; missing metrics are unknown and trigger a monitoring-health warning. Exact collector identity/roles/notification recipient need approval and provisioning. Alert evaluation and telemetry can incur costs.

Azure SQL: explicitly use free offer with freeLimitExhaustionBehavior AutoPause. Warn at20,000 and10,000 remaining free vCore-seconds, exhaustion0; separately monitor data/backup storage against32GB allowances. Pausing SQL does not stop Functions/storage/network charges.

Total monthly budget remains UNSET pending parent/user consent. Cost Management actual/forecast alerts should include storage, queue operations, network egress, telemetry/monitoring and compute overage. Suggested80/90/100% of the approved total budget; budgets and alerts do not stop billing, may lag and are not a hard cap. Do not automatically upgrade, set a spend amount, create contacts or send notifications.

Machine-readable proposal: deploy/azure/consumption-alerts.json. Threshold arithmetic is covered by Router.Checks.

Sources: https://azure.microsoft.com/en-us/pricing/details/functions/ ; https://learn.microsoft.com/en-us/azure/azure-functions/functions-consumption-costs ; https://learn.microsoft.com/en-us/azure/azure-sql/database/free-tier .

## Actual validation and current blockers

Official .NET SDK download/hash verification and version check passed. Local dotnet build/run stops before compilation: NuGet-Migrations mutex initialization attempts /home/agent/.dotnet and receives EROFS. DOTNET_CLI_HOME was set to the writable project but runtime shared-memory initialization still used the read-only home. No permissions were broadened or home reassigned. Therefore local C# compilation/tests have not passed.

Prepared credential-free Windows CI .github/workflows/dotnet-consumption.yml verifies official Windows OPA digest, runs real process tests and builds the isolated MCP project. No Azure login, secret, role, billing or deployment step is present. CI outcome must be recorded after publication. Core Tools download was previously denied403; do not retry via alternate routes. Windows CI success is not proof of Functions-host or Azure hosted support.

Next gates: Windows build/tests, actual local Functions MCP initialize/list/call, custom event-method integration, SQL/outbox implementation/tests, account and spending approval, reviewed resource plan, then hosted synthetic lifecycle/signature/retry checks. No real GitHub hook is included.

## Verified Windows CI result

[Run40182986503](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40182986503), implementation commit2dd865dd2ad766a377817b26d0d93a2dfdc0d8a0, completed SUCCESS. Job121137784962 ran the pinned Windows OPA1.9.0 executable after SHA256 validation. All13 checks passed: match, nonmatch, unknown subscription rejection, forbidden network builtin, malformed policy/input, four concurrent evaluations, four allowance checks, arbitrary destination URL rejection and cancellation. The .NET10 isolated Functions/MCP project built with zero warnings and zero errors.

This establishes Windows process-level OPA interoperability and C# MCP project compilation. It does NOT establish a real Functions-host initialize/tools/list/tools/call exchange, hosted child-process permission, SQL durability, event-extension compatibility, alerts delivery or a deployed Azure service. No Azure credentials were used by CI.

Additional source inspection: Azure/azure-functions-mcp-extension at fffb20b38ce7665443c1ae1dbffeaf4e5e2d66ee registers the MCP server in the WebJobs host process (McpWebJobsBuilderExtensions.cs). FunctionsMcpServerOptionsSetup advertises tools/resources/prompts. This is separate from the isolated C# worker DI container; adding middleware only to the worker does not establish a way to add events/* methods to that host server. A supported host extension hook or a deliberate SDK HTTP endpoint still needs verification.
