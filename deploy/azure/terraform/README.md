# Azure router adoption: first local diff, not deployment complete

Selected GitHub environment: azure-router. Keep keycloak-router-admin and repository OIDC customization unchanged. Proposed Azure FIC issuer https://token.actions.githubusercontent.com; subject repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router; audience api://AzureADTokenExchange. This binds environment/repository, not workflow filename. Native operator owns main-only environment protections/reviewer and Entra/bootstrap grants. No fleet identity reuse.

## Proposed initial bootstrap scope

Dedicated user-assigned managed identity webhook-mcp-router-f7076f8e38-github-deploy with this FIC; never attach it to the application and no client secret. This supersedes the earlier Entra-app proposal. Ten custom action-specific read roles assigned at the twelve exact inventory resource scopes; see adoption-role.proposed.json. Do not assign their combined permissions at resource-group scope: that would also permit SQL master reads. Server read is assigned at server scope, but databases/read is assigned only at the router database. Separate dedicated Standard_LRS state storage account whmcprtfstatef7076f8e38 (native preflight reports available; recheck at creation), private tfstate container, key router-poc.tfstate; AzureAD Blob data auth and native lease locking. Candidate custom blob data role scoped only to that container: read/write including required blob lease operations, without delete where backend behavior permits; prove the selected role before approval rather than silently falling back to broader Contributor. Backend lookup_blob_endpoint=false. Do not grant storage listKeys, appsettings/list, publishingcredentials/list, Owner, User Access Administrator, broad Contributor or SQL database access at this phase. State account/container bootstrap, encryption/access/retention/cost and grants require parent approval; existing$10/month alert budget unchanged.

Later deployment permission delta must be derived from selected exact app/package/config/queue operations, approved before apply. No roleAssignments write permission for the CI principal by default. SQL migration uses separate reviewed existing operator authority; Azure ARM grants do not confer SQL data permissions. No automatic network opening or resource-provider registration.

## Adoption mechanics and secret-read rationale

Terraform1.15.8, Azure/azapi2.13.0 signed provider and checked-in lock. Input inventory is exact existing IDs/names/types/parents/location from native read-only inventory, no app settings or credentials. All resources imported with explicit API versions. prevent_destroy plus ignore_changes=all deliberately freezes initial resources. Import plan guard rejects EVERY mutation including create/update/delete/replace; permitted result is no-op resources with imports only. No apply job exists yet. This establishes ownership safely before selective lifecycle management, not a claim of complete infrastructure convergence.

AzAPI resource Read/Import source performs ResourceClient.Get at the specified resource ID/API version. Allowed types exclude sites/config, and no action resources/data sources, listKeys or appsettings/list calls are configured. skip_provider_registration=true, enable_preflight=false. This source/config inspection supports a GET-only adoption route; actual Azure request telemetry remains untested until approved OIDC/inventory are available. Do not switch to conventional AzureRM Function/storage import and silently request broader secret reads.

Source: https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/services/azapi_resource.go

## Files and validation

main.tf + .terraform.lock.hcl, ci/azure-import-plan-check.py, ci/test-azure-import-plan-check.py and proposed .github/workflows/azure-router-plan.yml. Local provider install/signature succeeded, terraform validate and fmt check passed;39 plan-guard cases passed. No Azure authentication/plan/import/apply run. State-account-only hardening: TLS1.2, no anonymous blobs/shared keys, reviewed versioning/bounded soft delete. Preserve runtime storage shared-key behavior for existing Azure Files; never apply state hardening to that account. No workflow published or dispatched.

Native operator supplied all twelve verified resources; inventory.auto.tfvars.json and inventory-provenance.json record the exact IDs/API versions and upstream evidence hash. SQL master is excluded. Terraform plan JSON/state/logs remain private and are not artifacts. No local-state fallback. Workflow uses protected azure-router env, pinned checkout, manual main-only guard and id-token:write only on the plan job. OIDC endpoint/default repo subject config is unchanged.

## Subsequent runtime deployment work

Preserve SQL useFreeLimit/AutoPause and closed stopped app until separately approved activation. Adopt existing infrastructure, then introduce explicit nonsecret desired properties and plan guards without replacing SQL/storage. Resolve package upload/status path after earlier Forbidden, exact packagehash/source, runtime secret-reference mechanism, SQL/queue grants and dip config before producing an apply/deploy job. This adoption path does not intentionally request the Azure Files key; it does not guarantee secret-free state. Do not overwrite appsettings as a partial map or request broad secret read to merge them without explicit approval. A secret-reference configuration store/access mechanism is a separate exact proposal, not assumed provisioned.

## Bootstrap handoff — proposed, not applied

1. Native operator checks name availability and creates the dedicated deployment UAMI, the separate state account and private container. Azure server-side encryption at rest, HTTPS/TLS1.2, Standard_LRS, shared-key access disabled. Proposed state retention: blob versioning plus seven-day blob/container soft delete, and a lifecycle rule removing previous versions 30 days after their creation, not after becoming noncurrent; never delete the current state blob. Review storage costs under the existing budget. This is authenticated public-endpoint storage for GitHub-hosted runners, not a private-endpoint network claim; no anonymous access. Network posture requires approval.
2. Create the exact federated credential in federated-credential.proposed.json. Protect environment azure-router with main-only deployment, Robert review, allowed self-review and no administrator bypass. Preserve repository OIDC customization and the separate Keycloak trust.
3. Create the ten action-specific custom read roles and twelve scoped assignments in adoption-role.proposed.json. Assign state-role.proposed.json only at the new account's `/blobServices/default/containers/tfstate` scope. Replace the principal placeholder with the new UAMI's principal ID; never use a runtime/fleet identity. CI gets no role-definition/assignment write permissions.
4. Set environment variables AZURE_ROUTER_CLIENT_ID (new UAMI client ID) and AZURE_ROUTER_STATE_ACCOUNT (verified state-account name). No client secret. Review/publish the manual workflow, then run the initial plan under protected approval. No apply step is present: successful plan does not yet import resources into state.

Backend read/write is real state data access, not read-only Azure infrastructure access. Terraform may create an empty state blob during initialization and writes lock metadata. Source review of Terraform 1.15.8 shows Get/GetProperties/ListBlobs, PutBlockBlob/SetMetaData and Acquire/ReleaseLease; blob lease authorization uses the blob write data action. The proposed role includes blob read/write, excludes delete; workspace deletion/state deletion are unsupported. No live role/backend test has occurred. If a required operation is denied, stop and identify it; do not fall back to storage keys or Contributor.

Source references:
- https://github.com/hashicorp/terraform/blob/v1.15.8/internal/backend/remote-state/azure/client.go
- https://github.com/hashicorp/terraform/blob/v1.15.8/internal/backend/remote-state/azure/backend_state.go
- https://learn.microsoft.com/en-us/rest/api/storageservices/lease-blob

The source/API checks do not replace a live OIDC plan. Local validation covers schema and guard behavior only. Actual Azure GET telemetry, import serialization and storage-role compatibility remain the first approved run's acceptance criteria. Plan output/state/logs stay private; no artifacts uploaded. A lease surviving runner termination may need operator-reviewed unlock, never automatic force-unlock.

## Independent-review corrections

AzAPI ImportState can retain the full flattened ARM GET body/default output even with body={} and response_export_values=[]. Do not describe resulting plans/state as metadata-only or guaranteed secret-free. Private encrypted remote state and private ephemeral plan/log handling are mandatory. App-settings/list and listKeys remain excluded from intended calls and grants.

The guard requires Terraform 1.15.8, JSON format 1.2, complete exactly true and errored exactly false. It rejects nonempty/malformed action_invocations and deferred_action_invocations as well as deferred resource changes. Versions come from the pinned Terraform source: https://github.com/hashicorp/terraform/blob/v1.15.8/internal/command/jsonplan/plan.go .

Native preflight reports westus2 Hot LRS at $0.0184/GB-month. Its conservative scenario of 1 GB including versions plus 10,000 each write/list/read/other operations totals about $0.1264/month, excluding bandwidth and tax. This is a usage estimate, not a cap or a local billing verification. Keep the existing $10 budget; version growth and transactions remain chargeable. The new identity's exact resource GETs, absence of unwanted permissions, and backend lease operations must pass after approved bootstrap. Rejected narrow assignment scopes require review, not broader-role fallback.
