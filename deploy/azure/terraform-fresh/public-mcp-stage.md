# Public authenticated MCP activation (prepared, not executed)

The user selected public HTTPS ingress and Keycloak client credentials. This stage
changes only the existing Function's enabled flag, publicNetworkAccess and main
site default ingress action. SCM remains deny-all. Azure site restrictions apply
to the whole main site: this also makes the signed webhook route network-reachable
and does not by itself hide the packaged legacy MCP extension route. No webhook
registration or destination is created. Verify auxiliary routes reject unauthorized
access; do not describe network-public ingress as anonymous application access.

Exact Terraform inputs, in addition to existing backend/admin configuration:

```hcl
runtime_ready       = true
app_enabled         = true
public_http_enabled = true
public_mcp_ingress  = true
http_allowed_cidrs  = []
sql_outbound_ips    = []
dispatch_enabled   = false
package_sha256     = "2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c"
```

The manual `azure-router-public-mcp.yml` workflow uses the existing deployment
OIDC identity and protected azure-router environment. It requires exact reviewed
main SHA, explicit confirm_public_mcp, and operator-set
AZURE_ROUTER_RUNTIME_CONFIG_VERIFIED=true. That readiness variable is an operator
attestation, not a substitute for actual reference resolution or endpoint tests.
Only set it after the three private values have been verified, including the
actual Keycloak client/subject mapping. No secret value enters the job or Terraform.

The guard validates both pre-update and post-update snapshots using the existing
closed-stage contract after explicitly projecting just the three authorized
activation fields back to their closed values. It requires the other twelve
resources to be no-ops, forbids app creation/replacement and any other applied
input delta, and fixes the deployed package digest. It rejects write-only overrides,
unknown applied inputs, SQL changes, settings additions, dispatch changes and SCM
opening. A refreshed post-apply plan must be entirely no-op. Existing closed-stage
guards remain unchanged. No automatic retries or rollback on uncertain apply.

Existing resource-manager permissions cover the app update. This workflow adds no
IAM grants and has no Key Vault value read/write or credential creation steps.
Secret provisioning remains with the separately authorized native operator.
The DIP operator must verify the protected credential installation destination and
client-credentials support. Do not use the management federation as an application
token or put client secrets in GitHub variables, logs, artifacts or Terraform.

First acceptance: host starts under existing storage permissions; no persistent
background faults; no-token/malformed/wrong-audience/unmapped-client requests denied;
valid DIP token initializes /api/mcp and calls tools/list. Cross-tenant tool access
and request-log persistence cannot be declared verified by initialize/tools/list:
SQL remains closed, so those require a separate exact app-egress SQL network stage.
No optional dispatch is required for this first slice. Broad runtime review remains
issue10; a failure in required host startup must be diagnosed without queue CRUD
permission expansion. No live acceptance test has run for this stage yet.
