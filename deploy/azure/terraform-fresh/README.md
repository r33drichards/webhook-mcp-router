# Fresh replacement — proposal only

Canonical naming is the v2 contract: rg-webhook-mcp-router-v2, webhook-mcp-router-v2-f7076f8e38, asp-webhook-mcp-router-v2, whmcprv2f7076f8e38, sql-webhook-mcp-router-v2-f7076f8e38/router, kv-whmcprv2-f7076f8e38 and the three webhook-mcp-router-v2-f7076f8e38 SQL identities. The overlapping -tf naming suggestion was withdrawn by the native planner.

Existing control-plane RG/state account/deployment UAMI/FIC must remain untouched by resource lifecycle operations. Reuse the protected state container with key router-v2.tfstate, not the historical router-poc.tfstate. Native bootstrap must extend the existing previous-version retention filter to tfstate/router-v2.tfstate as well; delete previous versions only after 30 days from creation. Never delete current state blobs. No lifecycle change has been performed here.

The $10 total router monthly budget must cover both exact old and new RGs through one operator-managed subscription-filtered budget, preserving the existing old budget until verified. This includes overlap, state, vault, storage/network and runtime costs; alerts are not a cap.

Terraform creates fresh resources, with deletion prevented. No import, shared-resource mutation or old-runtime cleanup is included. Initial app is disabled, public networking disabled, main/SCM default-deny. Private Blob package and system-assigned identity replace Azure Files/keys. runtime_ready gates creation until package and approved identity/secret-reference bootstrap are ready; it does not activate the app. Key Vault is proposed for runtime JSON references only; secret values never enter Terraform inputs. Exact grants and new vault costs need approval.

Validation to date: Terraform init without backend, format/validate and synthetic fresh-plan guard fixtures only. No live new-resource plan/apply or hosted replacement acceptance has run. Actual LocalDB migration and Functions-host qualification subsequently passed as recorded below.

## Vault ownership and network approval

Vault kv-whmcprv2-f7076f8e38 is operator-owned, outside Terraform resource lifecycle and CI resource grants. Proposed public HTTPS endpoint with Entra RBAC, no anonymous access, bypass None, exact control-UAMI get permission on router-auth, router-tenants and router-delivery-keys only. App Service reference requests can originate outside the app's outbound-IP list; Windows Y1 has no VNet integration, so default-deny vault/IP allowlisting is not asserted to work. Native operator must approve/bootstrap this explicit network choice and secret scope; no vault or secret was created. Alternative operator-managed protected app settings would avoid the vault but require careful merge/config ownership outside Terraform and potential setting reads; it is not silently selected.

The deployment principal cannot manage vault security or directly read secret values under this proposal. Nevertheless a code publisher can run code as the app's identities, which can read authorized runtime secrets. Review/publish controls are part of the secret trust boundary.

## Validation gaps and exact next qualification commands

Local .NET SDK 10.0.402 does exist at `.tools/dotnet/dotnet` (it was not on PATH). Core Tools directory is empty. Prior official npm install failed fetching `https://cdn.functions.azure.com/public/4.0.281211/Azure.Functions.Cli.linux-x64.4.12.0.zip` with HTTP403; no alternate route or blocked download was retried. Thus no local Functions host/queue-extension runtime pass is claimed. Local Docker has only Keycloak images; no SQL server or pyodbc is installed. Do not label mock migration tests as SQL execution.

Prepared `ci/azure-sql-migration-localdb-check.py` for the existing Windows CI LocalDB runner. It executes the exact Python migration orchestration against real SQL using integrated Windows identity: rollback on failed grants, exact eight-table commit, repeat rejection and cleanup. It deliberately uses a synthetic WITHOUT LOGIN principal, so it does not prove Azure Entra TYPE=E SID grants. Requires pyodbc plus the runner's ODBC Driver17/18; executed successfully in Windows CI40254393996. The local test TLS exception is confined to LocalDB, not the production migration code.

Pinned queue components are Worker.Extensions.Storage.Queues5.5.4 and Azure.Storage.Queues12.28.1. Actual pinned-host poison/startup behavior passed in CI40254393996; Azurite cannot prove Azure RBAC authorization. Candidate queue roles must not be called qualified solely from SDK source or emulator success.

## Ordered bootstrap (no circular system-identity prerequisite)

1. Foundation creates plan/storage/queues/private package container/SQL and three UAMIs. Native operator manages vault and approved control-UAMI secret reference reads. Upload verified ZIP under its SHA256 object name.
2. Set runtime_ready=true to create the DISABLED, network-closed app. Control-UAMI secret-reference access can exist already; system identity does not exist until this creation. Do not claim package/host access succeeds at this stage.
3. Native operator obtains the new app system principal and grants exact host/package/queue authority. Execute migration and render runtime secret JSON using the NEW client IDs; never reuse old-router IDs.
4. Only after configuration/grants/readiness pass, review activation/start/trigger-sync and exact application ingress restrictions. SCM stays default-deny.

Queue sender reads AzureWebJobsStorage__accountName=whmcprv2f7076f8e38 and explicitly uses SystemAssigned. Queue trigger uses RouterQueue__queueServiceUri=https://whmcprv2f7076f8e38.queue.core.windows.net and RouterQueue__credential=managedidentity (no client selector). Both use the new app system identity. SQL endpoint is sql-webhook-mcp-router-v2-f7076f8e38.database.windows.net. sql_identity_ids output provides NEW client/principal IDs for operator validation, not secrets.

## Delivery key configuration is a third protected reference

ROUTER_DELIVERY_KEYS_JSON references router-delivery-keys in the operator-owned vault. Shape: {"mcp-js":{"approved_key_alias":"BASE64_24_TO_64_BYTE_SECRET"}}. This is an explanatory placeholder, not a usable key or a secret to commit. With no configured destinations, {"mcp-js":{}} is a closed staging value; it does not prove delivery readiness. ResolveAsync reads this setting when resolving a selected delivery key, not in the resolver constructor. Actual outbound delivery requires a separately approved destination and matching alias/key. Include third-secret get scope in the same not-yet-approved bootstrap bundle; no new live credential has been generated.

All five SQL connection fields remain inside ROUTER_TENANTS_JSON: RegistryReadConnection uses the fresh reader client; RegistryWriteConnection/LogReadConnection use fresh control; OutboxConnection/LogWriteConnection use fresh delivery. No extra standalone SQL app settings are introduced.

## Declarative activation and conditional package publishing

Activation settings are Terraform variables app_enabled, public_http_enabled, dispatch_enabled, http_allowed_cidrs and sql_outbound_ips, all closed/empty by default. SQL firewall rules are explicit desired resources. Native-only runtime toggles are not the intended source of truth; later Terraform must preserve the approved activation inputs. The current fresh-plan guard deliberately rejects activation/firewall additions until the exact reviewed activation contract and addresses are incorporated; it is not silently relaxed.

A digest filename alone is not immutable. ci/azure-package-upload.py uses overwrite=False plus If-None-Match:*, then downloads the resulting object and verifies size/SHA256. Existing objects fail closed, including reruns, pending explicit verification/reuse handling. A principal with Blob write can still deliberately overwrite through other code; publisher review remains a trust boundary. Five fake-client contract tests passed; actual Azure upload/readback has not run. No SAS/listKeys or publishing credential code is used.

First Windows qualification run40253717999 passed existing SQL integration, then the new LocalDB ODBC fixture failed because encryption is unsupported on its local connection. Fixture fixed to local IPC Encrypt=no with no remote-host parameter. Production migration still uses Encrypt=yes/TrustServerCertificate=no. Poison-host tests were not reached in that run.

## Completed Windows qualification

[Run 40254393996](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40254393996), source f7d2032c0fad1233641a9b5d899a4a8af54425ea, completed successfully. LocalDB proved rollback on grant failure, exact eight-table commit and repeat-migration rejection. Actual Core Tools host with the pinned queue extension consumed valid wakeups, retried invalid JSON and wrote the expected precreated poison queue. Authenticated MCP initialization, destination tools, tenant denial, signed ingress, redacted logs, fresh-host readback, real OPA routing to SQL outbox and dedup passed. Separate local HTTPS certificate-validation delivery tests passed in the same run.

This is not Azure RBAC, Entra SQL grants, hosted Keycloak/JWKS or hosted callback proof. Host fixture uses synthetic static signing keys and LocalDB; Azurite uses development authentication. The host test does not attempt a callback. No new Azure resources or secrets were created. The prior failing run is retained as evidence; production SQL TLS remains required.

The subsequent guard-only change adds closed-stage dispatch/ingress rejection: 15 local guard fixtures pass. Conditional package upload has five fake-client checks; actual Azure blob upload is still pending approval/execution.

## Cost/security guard hardening

The guard independently fixes Y1/Dynamic Windows, Standard_LRS HTTPS/TLS1.2 storage with shared keys and anonymous blobs disabled, private package container, SQL GP_S_Gen5_2 at min0.5/max2 vCores/32GiB/60-minute idle pause/free-limit AutoPause/local backup, Entra-only SQL and closed networking. App quota1000, scale1, HTTPS/TLS1.2, disabled FTPS/debug/always-on, and the exact fresh plan binding are checked. Forty-three fixtures include premium tiers, paid SQL fallback, capacity/storage increases, public/shared-key storage, old resource scope and activation rejection. Changing resource JSON alone does not relax the independently specified contract.

The Build workflow now executes these guard, package and migration-orchestration tests on every push/PR. Windows run40254393996 remains tied to f7d2032; subsequent changes concern guards/tests, Build workflow and documentation only. They do not change the Windows application, fixture, migration or Functions-host workflow. No claim that the Windows run executed on a later head is made.

## Reviewed foundation apply workflow (not dispatched)

azure-router-foundation-apply.yml is manual, main-only, protected by azure-router and an exact reviewed commit input. It runs guard tests, plans privately, restricts the plan to the twelve foundation resources (no app), hashes and applies that same guarded saved plan, then requires a refreshed no-op plan. The checksum detects local plan changes, not independent human approval. No activation, firewall, IAM, vault or delete resources are in this apply. Failed/partial creation is not automatically destroyed. Native bootstrap and workflow/code review must complete before dispatch. App creation remains a subsequent disabled stage after package/config preparation.

Foundation now precreates private azure-webjobs-hosts and azure-webjobs-secrets containers. Candidate host role is containers read/write plus blobs read/write/delete at only those two containers. Package read remains separate. No Blob Data Owner, account-wide wildcard or delegation-key fallback is proposed; actual Azure host authorization is still pending qualification.
