# Railway Keycloak Terraform proposal — issue #1

Design and validation only. No apply, state backend creation, realm/client mutation, token exchange, network access change, service restart or feature enablement is authorized here. Existing Keycloak 26.4.7 service remains 4 GB; existing `mcp` browser realm is outside these configurations. This does not work around the rejected live realm/client action.

## Provider and compatibility

Use official `keycloak/keycloak` 5.10.0, Terraform 1.15.8. Upstream lists 26.4.7 in its acceptance-test matrix. This is compatibility evidence, not proof of external access or privileges on the Railway instance. Version 5.9 introduced handling for 26.4+ restricted `/admin/serverinfo` responses. Both providers explicitly pin `keycloak_version="26.4.7"`; do not grant master/system-wide roles just to discover the version. Update this pin only after verifying an independently approved server upgrade.

- [Official provider](https://github.com/keycloak/terraform-provider-keycloak/tree/v5.10.0)
- [Version fix](https://github.com/keycloak/terraform-provider-keycloak/blob/v5.10.0/CHANGELOG.md)
- [Provider authentication/version configuration](https://github.com/keycloak/terraform-provider-keycloak/blob/v5.10.0/docs/index.md)

## Two separately authorized ownership boundaries

1. `bootstrap/`: a dedicated state key and one resource, new realm `webhook-router`, disabled by default with deletion protection. It requires an independently approved bootstrap principal capable of creating that realm, preferably a short-lived Keycloak access token. There is no Terraform master admin account, administrator role grant or credential resource. Inspect existing realm names before apply; if it already exists, stop and review/import only that exact realm instead of replacing it. Do not import `master` or `mcp`.
2. Out-of-band approved bootstrap step: create the confidential administration client `terraform-webhook-router` **inside webhook-router**, with service accounts on and interactive/password flows off; assign only the reviewed administration permissions for this module. This client and its own grants/credential are not managed by the ordinary realm stack. An existing admin must establish authority; Terraform cannot bootstrap itself from no access. Revoke temporary bootstrap authority after handoff.
3. `realm/`: authenticates to webhook-router, contains no realm resource and cannot select another realm. Manages a disabled `dip-webhook-router` confidential M2M client, three explicit read scopes and its router audience mapper. No arbitrary client URL/callback, admin grants or identity-provider trust resource. `prevent_destroy` is a guard against accidental deletion, not an authorization boundary.

Candidate least-privilege roles are realm-management `manage-clients` (client/scope/mapper mutation) plus only the view/query permissions actually needed by refresh/list. Verify the 26.4.7 role composites and endpoint behavior before granting; do not silently substitute `realm-admin`, `manage-realm`, `manage-users`, `impersonation`, master `admin`, or system/version permissions. `manage-clients` is broad within this NEW realm and can affect other clients there; it is not per-client isolation. If narrower client-specific administration is required, separately qualify 26.4 fine-grained admin permissions against every resource call. A 403 is a qualification failure, not permission to expand grants. Check that this account cannot read/manage `mcp` or create other realms, using approved read-only negative probes.

Expected routine plan: one confidential client, three client scopes, one authoritative default-scope attachment and one audience mapper. Scope attachments are authoritative **only for this new client**; no existing browser client is adopted. No write scopes are included by default. If dip requires destination mutation, review `destinations:write` separately. Map actual service-account subject, client ID and allowed scopes into the router's trusted configuration; tenant identity must not come from an untrusted token claim alone. dip must support client-credentials token acquisition. No DCR or user-login redirect is needed.

## State and credential handling

Both roots require an explicit `azurerm` backend; no usable backend location or credential is included. Propose private dedicated blob container with HTTPS, encryption at rest, lease-based locking, tightly scoped Entra data-plane access, audited access and approved backup/version retention. Use different keys and access boundaries for bootstrap and routine state. The shared application worker must have no state access. Root must approve backend provisioning, grants and incremental costs; do not reuse a public artifact, GitHub repository or broadly accessible application container. [HashiCorp backend reference](https://developer.hashicorp.com/terraform/language/backend/azurerm).

Treat state, plans, crash logs and `.terraform/` as secret-bearing even when provider attributes are marked sensitive. Never commit plaintext **or encrypted secret payloads**; `.gitignore` is only a secondary safeguard. Do not upload state/plan artifacts to this public repo, print `terraform show -json`, enable TF_LOG/KEYCLOAK provider debug, or place backend credentials in HCL/command-line arguments. Provider debug paths explicitly log token requests/responses.

Admin authentication comes only from the approved process environment: normally KEYCLOAK_CLIENT_SECRET for the restricted administration client, or KEYCLOAK_ACCESS_TOKEN for an already authorized short-lived **Keycloak** token. Clear conflicting password/JWT/secret variables when using a supplied token. No admin credentials in provider files or outputs. Provider-supplied access tokens do not refresh automatically; a long apply can expire. Bound runs and acquire a fresh authorized token for a separate run; no automatic privilege escalation/retry with master credentials.

Application client secret uses an ephemeral sensitive Terraform variable and provider `client_secret_wo` plus an explicit non-secret version marker, avoiding ordinary client_secret state storage. No random-secret resource or credential generation is included. An approved secret manager must independently supply/deliver the same credential to dip and Terraform. [Write-only provider contract](https://github.com/keycloak/terraform-provider-keycloak/blob/v5.10.0/docs/resources/openid_client.md). Provider bugs, imported resources or other fields can still expose secrets, so private state remains mandatory.

## Safe qualification sequence

- Offline: `terraform fmt -check -recursive`, each root `terraform init -backend=false -input=false`, `terraform validate`. These install the pinned provider but do not configure a backend, authenticate to Keycloak, run a plan or mutate resources. Lockfiles should record verified provider checksums.
- Pending approval: private state backend and external runner HTTPS/DNS/TLS reachability; exact approved administration identity; bootstrap realm creation, client and role setup; secret delivery/rotation. Console AdminAPI working does not prove provider network access or authentication.
- With that approval only: read-only version/discovery and scoped GET checks, then inspect a private plan with no deletes/replacements or references outside webhook-router. Saved plans are sensitive and must remain in approved private storage. Do not use `-target` or disable TLS to force a plan through.
- Review/apply is separate authorization. Afterwards qualify client-credentials token signature/issuer/audience/scopes and service-account subject without logging tokens, then router tenant denial tests. Existing mcp realm/service stays unchanged.

See `github-oidc.md` for the version-specific alternative to a long-lived administration secret. Jev remains issue #2 and is unrelated to this proposal.

## Validation recorded

On 2026-10-25, official Terraform 1.15.8 Linux archive checksum matched HashiCorp SHA256SUMS. Both roots completed `init -backend=false -input=false`, installing keycloak/keycloak5.10.0 with provider signing key A63FAED146E27E2A, then `validate` succeeded. Recursive formatting check passed. No backend initialized, plan/apply run, credential supplied or Keycloak endpoint contacted. These checks establish HCL/provider-schema validity only; least-privilege API access and runtime token behavior remain untested.

See [upgrade-proposal.md](upgrade-proposal.md) for the optional26.8.1 rehearsal/backup/rollback proposal. No upgrade is authorized or performed by this configuration.
