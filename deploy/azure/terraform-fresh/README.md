# Fresh replacement — proposal only

Canonical naming is the v2 contract: rg-webhook-mcp-router-v2, webhook-mcp-router-v2-f7076f8e38, asp-webhook-mcp-router-v2, whmcprv2f7076f8e38, sql-webhook-mcp-router-v2-f7076f8e38/router, kv-whmcprv2-f7076f8e38 and the three webhook-mcp-router-v2-f7076f8e38 SQL identities. The overlapping -tf naming suggestion was withdrawn by the native planner.

Existing control-plane RG/state account/deployment UAMI/FIC must remain untouched by resource lifecycle operations. Reuse the protected state container with key router-v2.tfstate, not the historical router-poc.tfstate. Native bootstrap must extend the existing previous-version retention filter to tfstate/router-v2.tfstate as well; delete previous versions only after 30 days from creation. Never delete current state blobs. No lifecycle change has been performed here.

The $10 total router monthly budget must cover both exact old and new RGs through one operator-managed subscription-filtered budget, preserving the existing old budget until verified. This includes overlap, state, vault, storage/network and runtime costs; alerts are not a cap.

Terraform creates fresh resources, with deletion prevented. No import, shared-resource mutation or old-runtime cleanup is included. Initial app is disabled, public networking disabled, main/SCM default-deny. Private Blob package and system-assigned identity replace Azure Files/keys. runtime_ready gates creation until package and approved identity/secret-reference bootstrap are ready; it does not activate the app. Key Vault is proposed for runtime JSON references only; secret values never enter Terraform inputs. Exact grants and new vault costs need approval.

Validation to date: Terraform init without backend, format/validate and synthetic fresh-plan guard fixtures only. No live new-resource plan/apply, actual SQL migration or hosted replacement acceptance has run.

## Vault ownership and network approval

Vault kv-whmcprv2-f7076f8e38 is operator-owned, outside Terraform resource lifecycle and CI resource grants. Proposed public HTTPS endpoint with Entra RBAC, no anonymous access, bypass None, exact control-UAMI get permission on router-auth and router-tenants only. App Service reference requests can originate outside the app's outbound-IP list; Windows Y1 has no VNet integration, so default-deny vault/IP allowlisting is not asserted to work. Native operator must approve/bootstrap this explicit network choice and secret scope; no vault or secret was created. Alternative operator-managed protected app settings would avoid the vault but require careful merge/config ownership outside Terraform and potential setting reads; it is not silently selected.

The deployment principal cannot manage vault security or directly read secret values under this proposal. Nevertheless a code publisher can run code as the app's identities, which can read authorized runtime secrets. Review/publish controls are part of the secret trust boundary.

## Validation gaps and exact next qualification commands

Local .NET SDK 10.0.402 does exist at `.tools/dotnet/dotnet` (it was not on PATH). Core Tools directory is empty. Prior official npm install failed fetching `https://cdn.functions.azure.com/public/4.0.281211/Azure.Functions.Cli.linux-x64.4.12.0.zip` with HTTP403; no alternate route or blocked download was retried. Thus no local Functions host/queue-extension runtime pass is claimed. Local Docker has only Keycloak images; no SQL server or pyodbc is installed. Do not label mock migration tests as SQL execution.

Prepared `ci/azure-sql-migration-localdb-check.py` for the existing Windows CI LocalDB runner. It executes the exact Python migration orchestration against real SQL using integrated Windows identity: rollback on failed grants, exact eight-table commit, repeat rejection and cleanup. It deliberately uses a synthetic WITHOUT LOGIN principal, so it does not prove Azure Entra TYPE=E SID grants. Requires pyodbc plus the runner's ODBC Driver17/18; syntax validated, not run yet. Existing Windows CI can execute it after source review/publication. The local test TLS exception is confined to LocalDB, not the production migration code.

Pinned queue components are Worker.Extensions.Storage.Queues5.5.4 and Azure.Storage.Queues12.28.1. Actual pinned-host poison/startup behavior remains to test; Azurite cannot prove Azure RBAC authorization. Candidate queue roles must not be called qualified solely from SDK source or emulator success.
