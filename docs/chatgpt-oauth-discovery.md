# ChatGPT OAuth discovery stage

This patch advertises the existing Keycloak issuer; it does not create an OAuth
client/user, enable registration, change token validation or complete a login.

- Resource: https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/api/mcp
- Metadata: https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/.well-known/oauth-protected-resource/api/mcp
- Issuer: https://keycloak-production-295b.up.railway.app/realms/webhook-router
- Advertised scopes: router:read, requests:read, destinations:read.

Unauthenticated and invalid-token MCP responses remain401 and add a fixed Bearer
WWW-Authenticate challenge pointing to this metadata. Insufficient scope remains403.
Metadata is public, needs no secret or tenant initialization, and never derives URLs
from incoming Host/Forwarded headers or token claims. No registration endpoint,
client secret, tenant mapping or request data is included. Host-level routePrefix
becomes empty so the RFC9728 path is correct; explicit api/ prefixes preserve the
existing MCP/webhook URLs. The legacy MCP extension is not removed by this change.

Resource metadata is a discovery identifier, not a change to the existing configured
JWT audience webhook-mcp-router. The actual ChatGPT authorization/token flow sends
resource with the canonical URL. Before claiming E2E, qualify the Keycloak audience
mapper and client configuration against that request, including rejection of wrong
audiences. Do not silently broaden the validator or change its expected audience.

ChatGPT uses user authorization-code + S256 PKCE, not service-account client
credentials. Copy its exact callback URI from the private plugin management UI.
A pre-registered client can avoid anonymous registration/experimental features if
that UI supports the selected client setup. Preserve issuer identification in all
successful/error authorization responses. Configure the exact user/client subject
mapping and limited read scopes; refresh tokens remain expiring and revocable.

Pending live work: non-admin account and secure password setup, exact callback and
client registration, private mapping update, reviewed rebuilt package deployment,
then browser login, refresh, invalid-token/tenant isolation and tools checks. Never
put passwords or tokens in chat/Git/CI output. Existing Origin denial is unchanged;
ChatGPT's server-to-server MCP transport should be qualified before any CORS changes.
SQL-backed exploration remains unavailable until separately scoped SQL connectivity.

Tests: eight compiled metadata checks locally; HTTP handler and actual Functions
host tests added to existing Windows CI. Their results are reported on the PR;
local source inspection is not a host boot or a live OAuth login.

References:
- https://developers.openai.com/plugins/build/auth
- https://www.rfc-editor.org/rfc/rfc9728.html
- https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/guides/securing-apps/mcp-authz-server.adoc
