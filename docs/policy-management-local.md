# Tenant-scoped policy management (PR qualification; not deployed)

Verified against main 3395eff4cbe23ceb2a1c00812b550e6171f2b871: MCP exposes request exploration and destination operations, but no policy management. SqlRegistrationWriter.SavePolicyAsync is internal and unversioned; it is not a hidden MCP command. GenericIngestion deliberately supports zero or one policy per tenant.

The local implementation adds these operations only for generic routing:

| Tool | Required additional scope | Effect |
|---|---|---|
| policies_get | policies:read | Read the tenant's active policy source, ID and opaque revision, or absent. |
| policies_validate | policies:test | Strict compile using the existing restricted OPA capabilities; no persistence. |
| policies_preview | policies:test, plus existing destinations:read | Evaluate candidate source against a caller-supplied original event and enabled tenant destination metadata; return a preview, never delivery. |
| policies_apply | policies:write | Compile then atomically create/update the one active tenant policy, using expected_revision. Affects subsequent ingress. |

Every MCP call still requires router:read and the existing validated issuer, audience, signature, expiry and trusted client+subject-to-tenant mapping. No tenant parameter, URL, auth setting, credential or destination registration is accepted. Unknown arguments are rejected before writes. Existing read grants and discovery scopes are unchanged. A separate approved Keycloak scope/client mapping and router allowed-scope update are needed before the agent can use these tools live.

Ownership is shared within the authenticated tenant, not a per-agent private policy. The existing Owner column is the tenant ID. An authorized collaborator can update that tenant's policy only with its current revision. SQL rowversion is opaque 16-character lowercase hex; null explicitly means first creation. A different ID, stale version, concurrent overwrite, or ambiguous existing multi-policy state is rejected. No per-actor audit history is added in this minimal slice. No delete operation: apply a default-deny policy to stop future routing.

Validation checks syntax/type/builtin capabilities, not correctness for every possible input. Preview uses the same generic OPA pipeline and registered enabled destination IDs as ingress. Context tenant/source/provider is server-owned; only event_type and original event are caller input. Redacted examples are untrusted and may omit fields; preview does not claim they are exact original requests. A compiled policy can still default-deny or fail at runtime. No preview can enqueue, sign or deliver anything, enable dispatch, add destinations or change source bindings. The registry is checked again for actual ingress/delivery.

Storage requires no schema migration: registry.Policies already has Owner, Id, Source and Revision rowversion. The control identity already has SELECT/INSERT/UPDATE/DELETE on that table; the new API uses SELECT/INSERT/UPDATE only. Serializable tenant-range locking plus expected rowversion prevents lost updates and enforces one policy. No Function DDL, new SQL grant or IAM grant is needed. Existing internal legacy SavePolicyAsync remains for legacy composition/tests and is not exposed through these tools.

Local validation: ci/test-policy-management-local.py compiles actual Router.Core with installed .NET10 Roslyn and runs the real installed OPA binary. 27 checks passed: valid/invalid/forbidden-network Rego, preview/default deny, cross-tenant destination rejection, no preview writes, limits, version conflicts, read-only scope denials and cancellation. Its storage is a test double, not SQL proof.

Added actual-SQL cases to Router.Integration: rowversion readback, stale/create conflict, second-policy rejection, same-ID tenant isolation, concurrent exactly-one-winner update and missing-scope denial. Added SDK tool catalog/read/scope/unknown-tenant tests to Router.McpChecks. These were NOT executed locally. Full dotnet build is blocked by the environment's NuGet-Migrations named-mutex IOException even with a writable DOTNET_CLI_HOME. Publication and disposable CI are now approved; results remain pending. Do not claim compiled Functions/SDK/SQL integration until CI verifies it.

Before release: run Windows LocalDB/SDK/actual Functions-host tests, independently review, then separately approve new user scopes/allowed binding and deployment. Native runtime SQL connectivity must be verified: the last supplied infrastructure evidence had SQL PNA disabled; successful MCP connection/tools enumeration alone does not prove registry SQL read/write connectivity. Do not open SQL/network or activate dispatch as part of policy API work.
