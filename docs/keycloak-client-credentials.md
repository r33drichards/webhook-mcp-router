# Keycloak client credentials for the Azure Functions router

Status: design update, 2026-10-25. No Keycloak deployment, client registration, secret creation, Azure authentication configuration or network change has occurred. No NixOS host has been selected. MCP remains hosted in C# isolated Azure Functions on Windows Consumption; Azure SQL remains the durable store.

## Confirmed direction

Use Keycloak on an existing NixOS host as the OAuth issuer, with pre-registered confidential service clients using client credentials. Managed External ID is not the selected issuer. This controlled machine-to-machine setup does not require dynamic client registration or experimental MCP registration features. Each actual MCP client must be able to acquire a token and supply an Authorization Bearer header, then obtain a replacement before expiration. Compatibility with any particular interactive MCP client is not established by choosing OAuth.

Clients authenticate to Keycloak, not to the router with their client secret. The router validates access tokens using public signing keys; it does not need each client's secret. Client credentials identify a service, not an end user. This does not solve future browser/admin UI login.

## Required resource-server boundary

Validate every MCP HTTP request before dispatch: cryptographic signature with an explicit allowed algorithm set, exact configured realm issuer, router-specific audience, expiry/not-before with bounded skew, and operation-specific permissions. Trust discovery/JWKS only from operator-configured issuer endpoints over verified HTTPS; never fetch URLs from untrusted token headers or claims. Bound and cache key refresh; test rotation and concurrent unknown-key requests without accepting unverifiable tokens.

The proposed scopes are router:read, subscriptions:write, policies:test and policies:write. These are design names, not configured grants. Keycloak client scopes, role mappings and audience mappers must be configured deliberately: requesting a scope must not grant permissions the service account lacks. Roles and OAuth scope strings are different claims and need an explicit mapping contract.

After token validation, resolve the validated Keycloak authorized-party/client identity (for example azp, verified against actual issued tokens) through an operator-controlled mapping keyed by exact issuer and client ID to one internal tenant ID and allowed permissions. Require a registered service-account identity, not merely a nonempty azp; define and test the expected subject/service-account relationship. Never use request parameters, tenant headers, client-supplied arguments or an arbitrary token tenant claim as the tenant authority. Reject unmapped/disabled clients. Keep tenant ID separate from actor/client ID so multiple approved clients may share one tenant without conflating audit identity and ownership.

Return 401 for invalid/missing credentials and 403 for insufficient permission, without browser redirects or token logging. Use short-lived access tokens and define revocation expectations: offline JWT validation alone does not immediately revoke already issued tokens. Local mapping disablement can deny a client on the next authorization check; caching affects that delay.

## Fit with current code and concrete remaining changes

1. The published Functions endpoint currently uses an MCP system key and only exposes router_status. No Keycloak JWT validation exists. Keep that existing protection until a tested replacement covers the real endpoint. Do not label a system key OAuth.
2. The Functions extension hosts /runtime/webhooks/mcp in the WebJobs host, outside the isolated worker's DI container. Choose and validate a host-level authorization integration or an explicitly SDK-owned HTTP endpoint. Adding worker middleware alone is insufficient evidence. Custom events/* support remains a separate host integration gate.
3. Azure documents a custom OIDC provider for App Service/Functions, but that guide describes interactive login and provider-specific audience constraints. It is not proof that this exact Keycloak client-credentials bearer flow works on the selected Functions/MCP route. Test bearer-only requests and identity propagation before choosing Easy Auth as the enforcement boundary. Never trust externally supplied principal headers without a verified platform boundary.
4. Unpublished registration code already filters SQL reads/writes by Owner and includes owner in subscription identity. Replace ambiguous owner strings at entry points with a trusted authorization context carrying tenant ID, actor ID and permissions. The current string parameter is not authentication.
5. Secure multi-tenancy is not implemented. Add tenant scope to ingress source lookup, callback/secret ownership, receipt uniqueness, outbox rows/claims/leases/retries and audit records. The current receipt key is Source plus DeliveryId and outbox claims are global. A tenant token must not influence another tenant's policies or delivery state. Preserve receiver read-only registration access and separate outbox authority; neither permission split nor Keycloak alone supplies tenant isolation.
6. Provider webhooks continue to use raw-body signature verification with a server-configured source-to-tenant mapping; GitHub does not need to acquire an MCP OAuth token. Outbound callbacks retain the verified event extension's signing/verification convention. OAuth management credentials must not become webhook signing keys or callback credentials.

## Acceptance tests before deployment

Use synthetic keys/tokens and loopback fixtures only: valid registered service client; wrong issuer/audience/signature; expired/future token; unknown client; missing scope; spoofed tenant input; disabled mapping; signing-key rotation; bounded concurrent token/JWKS refresh. Exercise initialize, tools/list, tools/call and the actual events/* methods through the real Functions host, not only a domain-service unit test. Verify no protected operation bypass through an alternative route or a notification request.

For two synthetic tenants, test policy/subscription read and write denial across tenants, same provider delivery IDs without collisions, callback/key isolation, tenant-aware outbox claims and renewal/unsubscribe boundaries. These are required tests, not passing results. Existing Windows CI establishes OPA process interoperability and C# compilation only.

## Pending approvals and decisions

Select the NixOS host, stable HTTPS issuer/realm, router audience, actual client software and client-to-tenant administration model. Keycloak version/Nix pin, persistence/backup and availability plan remain to be reviewed. Deployment, registrations/secrets, DNS/TLS/network/roles and Azure billing/provisioning are pending explicit authorization. No secret values belong in this repository. No infrastructure action was attempted or denied in this design update.

## Primary sources

- [Keycloak server administration: service accounts, client scopes and audience mappings](https://www.keycloak.org/docs/latest/server_admin/index.html#_service_accounts).
- [Keycloak OpenID Connect endpoints and flows](https://www.keycloak.org/securing-apps/oidc-layers).
- [Azure Functions MCP binding](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-mcp).
- [Azure App Service/Functions custom OIDC provider](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-openid-connect). Its interactive-provider documentation is not an end-to-end M2M validation result.


## Implementation checkpoint (not endpoint readiness)

The latest user instruction authorizes implementation. Router.Auth now uses pinned Microsoft.IdentityModel.JsonWebTokens 8.14.0 for signature/issuer/audience/lifetime/RS256 validation, checks service-account subject and azp against a trusted mapping, and intersects issued scopes with mapping grants. Fixed HTTPS JWKS retrieval has size/time/key-count limits, serialized cache refresh and an unknown-key refresh cooldown. Token-controlled URLs and redirects are not used. Mapping-disable hot reload is not implemented; replacement/restart is currently required.

The local implementation adds TenantContext-bound registration/outbox stores, tenant-scoped receipt uniqueness and lease updates, and request-log storage. Fresh synthetic schema only: no upgrade migration for existing databases is provided. Direct SDK compiler validation passed for Router.Core and Router.Auth. All 13 existing OPA checks and 13 OAuth checks passed locally. Direct compilation emitted CS1701 reference-unification warnings for net8 IdentityModel assemblies against net10 reference assemblies. This is not a normal dotnet build or Functions-host result. SQL and full-project CI remain pending. This does not yet protect the actual Functions MCP endpoint, wire events/*, or establish hosted multi-tenancy. No real token or credential has been created.

Request logging defaults: seven-day logical retention, 10,000 rows per tenant, 64 KiB input and 8 KiB sanitized payload ceiling. No raw path/query, arbitrary headers, supplied correlation IDs, malformed raw text or unauthenticated payload is stored. String values are redacted by default, with additional configurable sensitive field names. Logs carry generated correlation IDs and explicit completeness/redaction flags. Expired rows are hidden immediately by queries and pruned on writes; an independently scheduled physical-retention purge is still required for inactive tenants. Pagination is tenant-bound, descending sequence, with a 100-row maximum. Logs and dedup receipts are separate. A LoggedIngress wrapper now persists accepted, duplicate, rejected and failed attempts after trusted source resolution, omitting unverified payloads. A tenant-bound purge operation deletes up to 1,000 expired rows per call; scheduling it is outstanding. MCP endpoint exposure and HTTP composition remain outstanding; domain exploration methods do not authorize policy creation.

## SDK endpoint integration update

A dedicated HTTP-triggered `/api/mcp` implementation now authenticates the bearer token before parsing/dispatching every request. It uses official ModelContextProtocol.Core 2.3.0 (tag v2.3.0, commit 9a327829ef066c44a0d737c58bf3c7617d7c701c), its stateless StreamableHttpServerTransport, built-in tool handlers and its experimental custom-method hook for events/*. That SDK extension hook is distinct from OAuth dynamic client registration. The compatibility filter adds the verified top-level events capability to initialize results. The older `/runtime/webhooks/mcp` system-key route still exposes only the historical readiness tool; it is not the new bearer route.

Local direct-compiler/SDK execution passed five assertions: initialize events capability, tools/list in a fresh instance, exploration tools/call in a fresh instance, events/list, and no recursive webhook capture. This is real SDK execution but not a live Functions host. HTTP handlers, deployment composition and real JWKS network behavior still need host-level integration tests. No Azure or Keycloak endpoint was configured. The server restricts this POC to protocol version 2025-06-18 and non-browser clients (Origin requests rejected); UI authentication is separate work.

The webhook HTTP function resolves its source to an operator-configured tenant, reads at most 65,537 bytes, then calls LoggedIngress. Unknown sources get no tenant log. Source-attributable invalid signatures produce metadata-only rejected entries; oversized input is marked truncated without payload. Log persistence failures return failure rather than claiming complete logging. Database and callback settings are loaded only from operator environment configuration; no actual configuration values are committed. RO/RW/log/outbox connection strings remain separate configuration entries, although one process possessing them is not a strong credential-isolation boundary.

CI run40185258405 passed OPA/auth checks but found nvarchar(4096) invalid; fixed to 4000. Run40185382439 reached tenant policy/subscription/receipt assertions, then exposed pooled isolation incompatible with READPAST. Claim now sets READ COMMITTED explicitly. These failures are retained as evidence, not presented as passing SQL tests.
