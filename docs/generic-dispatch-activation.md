# Generic dispatcher activation handoff

Implementation is local/CI code, not live configuration. Azure remains stopped and closed. Jev is deferred to issue #2.

## Required migration and permissions

Apply `src/dotnet/Router.Storage/schema.sql`, then `destination-schema.sql` through the approved migration operator. Fresh identifier columns use Latin1_General_100_BIN2 so SQL tenant comparisons match ordinal application identity comparisons. These scripts do not alter existing columns: inspect existing schema and dependencies before any migration; do not activate against case-insensitive tenant columns.

Additional object grants for the existing narrowly scoped identities:

- Registry reader: SELECT registry.Destinations; no access to delivery.DestinationConfig.
- Registry control writer: SELECT, INSERT, UPDATE registry.Destinations; INSERT delivery.DestinationConfig only. No DELETE, UPDATE, ALTER or ownership on protected bindings.
- Delivery identity: SELECT delivery.DestinationConfig and registry.Destinations; SELECT, INSERT, UPDATE delivery.WebhookOutbox, plus existing receipt/log authority.

The immutable-binding trigger blocks UPDATE. An endpoint change requires a new destination ID; disable the old metadata. Never grant application identities DDL/owner authority or protected-binding DELETE. Tenant isolation is enforced in application queries; these shared identities are not per-tenant SQL principals.

## Queues and protected settings

Operator must create `router-dispatch` and `router-dispatch-poison` in the existing router storage account. Queue sender/trigger requires the Function identity's Storage Queue Data Contributor role scoped to these queues or the router storage account. This is an additional grant, not performed by this code.

Configure `RouterQueue__queueServiceUri=https://<router-account>.queue.core.windows.net` and `RouterQueue__credential=managedidentity`; `AzureWebJobsStorage__accountName` must be the same approved router account. Sender uses ManagedIdentityCredential only; no developer credential fallback or account key. Host storage identity configuration remains separately required.

Until all gates pass, retain `AzureWebJobs.RouterDispatch.Disabled=true`, `AzureWebJobs.RouterReconcile.Disabled=true`, and omit `ROUTER_DISPATCH_ENABLED` (or set false). Activation requires enabling both functions and setting `ROUTER_DISPATCH_ENABLED=true`.

`ROUTER_TENANTS_JSON` adds optional `DestinationBindings`, each with `Id`, HTTPS `Endpoint`, and `SigningKeyReference`. These are operator-approved private bindings, not caller-supplied URLs. MCP returns binding IDs only; destinations_register selects one, assigns a new destination ID and starts disabled. Explicit destinations:write enables/updates metadata. destinations:read lists metadata with bounded keyset pagination. No management tool returns URLs or signing references.

`ROUTER_DELIVERY_KEYS_JSON` is a protected app setting shaped as a tenant-name map of key-alias to base64 signing key (24–64 decoded bytes). No values are included here or created by the implementation. Alias lookup is exact and tenant scoped. Use separate ingress and callback secrets; never put credentials in destination names/tags. Dispatcher clears its owned decoded key buffer after each attempt. This setting-based resolver is not a Key Vault integration and requires normal operator secret-rotation procedures.

## Scheduling and delivery semantics

SQL receipt/outbox transaction commits before a queue wake-up. Queue messages contain only tenant/source IDs, not payloads or credentials. A failed send returns a retryable ingress failure; duplicate delivery retries can signal again. A daily 03:17 UTC timer re-signals configured sources, bounding missed-wakeup recovery to approximately one day without frequent SQL polling that prevents auto-pause. This is a deliberate POC latency/cost tradeoff, not an atomic SQL/queue transaction.

Worker processes at most two deliveries per 25-second invocation and re-signals after 30 seconds when work was found. Outbox uses leases and at most five attempts. Queue host retries at most five times and sends failures to the poison queue. Monitor poison messages operationally; no automatic poison replay is implemented. Delivery is at least once: receivers must deduplicate X-Webhook-Delivery. Disablement is rechecked before delivery; an in-flight request may already have started.

HTTPS is limited to DNS hosts on port443, no credentials/query/fragment, redirects or proxy. DNS answers must all be public and the connection is pinned to a validated address. Standard TLS hostname/certificate validation remains enabled. The internal test constructor uses an ephemeral test CA and maps the validated fixture address to loopback; it is not a production configuration switch and does not change machine trust.

## Evidence and remaining gates

Local real HTTPS tests verify exact signed body receipt, wrong-host/untrusted/expired certificate rejection, no redirect follow, DNS pinning, and pre-connect rejection of mixed public/private addresses. MCP SDK tests verify disabled registration, explicit enabling, scope checks and cross-tenant isolation. These tests do not establish Azure queue, SQL network, Keycloak or hosted callback readiness. CI and final package references will be recorded after completion.

Before activation: reviewed migrations/grants, queue provisioning and role, approved Keycloak realm/client mapping, destination registration/credentials and receiver signature agreement, fresh Windows package, actual host/queue tests, controlled hosted E2E, then separately approved GitHub all-event hook for mcp-js. No real hooks, credentials, external deliveries or Azure changes are made by this handoff.
