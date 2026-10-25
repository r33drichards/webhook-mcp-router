# Phase 2: closed Azure resource preparation

Prepared, not Azure-validated or deployed by this task. Supervisor is the sole Azure writer. User approved current Azure user as SQL administrator, narrowly scoped router managed identities and protected Azure Files settings. Exact SQL firewall rules and Keycloak remain pending. Budget is $10 with accepted overshoot risk; no new paid tiers.

## Preconditions and resource changes

Confirm PAYG, free SQL eligibility in westus2, existing dedicated RG/Windows Y1 plan/Standard_LRS storage ownership and budget. Do not overwrite another app or an existing app's settings with this fresh-provisioning template. Inspect for existing app/server/identities before each retry. SQL provider registration may be necessary; do not add providers or roles unrelated to this resource set.

`main.json` references existing storage/plan and creates:
- Entra-only SQL server, current verified user administrator, TLS1.2, public network disabled; no firewall rules.
- Database router, GP_S_Gen5_2, 0.5–2 vCores, auto-pause60min,32GiB, free-limit exhaustion AutoPause, local backup redundancy. If free offer rejected, STOP; never switch to BillOverUsage.
- Three user-assigned identities named `<app>-registry-reader`, `<app>-control`, `<app>-delivery`.
- One1GiB-quota Azure Files content share router-content. This quota is a storage bound, not a prepaid size or hard total cost cap.
- Windows .NET10 isolated Functions4 app, enabled=false, publicNetworkAccess=Disabled, maximumscale1, dailyMemoryTimeQuota1000GB-s, TLS1.2, FTPS/debug disabled. Missing ROUTER_AUTH_JSON/ROUTER_TENANTS_JSON also fails closed in the app.
- App system identity with Storage Blob Data Owner on ONLY the existing router storage account. No subscription-wide roles or SQL Directory Readers grant.
- AzureWebJobsStorage uses system managed identity. Azure Files uses a storage key expression evaluated inside ARM and stored in protected app settings. No key outputs or local exports. Do not log app-setting lists, deployment request bodies after resolution, keys or access tokens.

ARM API/property references:
https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers
https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases
https://learn.microsoft.com/en-us/azure/templates/microsoft.web/2024-04-01/sites
https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections
https://learn.microsoft.com/en-us/azure/azure-functions/storage-considerations

## Execute using supervisor's existing authenticated CLI

Use existing names from phase1, not newly derived guesses. Set SUB, RG, STORAGE, PLAN, APP, SQLSERVER to verified router-only values. Resolve the signed-in user's object ID via normal authenticated directory read; no new app credential is required. `ADMIN_LOGIN` is that approved user's login. GUIDs/login are parameters, not committed configuration.

```sh
az ad signed-in-user show --query '{id:id,userPrincipalName:userPrincipalName}'
az provider show --subscription "$SUB" --namespace Microsoft.Sql --query registrationState
# Register only if still needed for this approved SQL provisioning:
az provider register --subscription "$SUB" --namespace Microsoft.Sql --wait
az deployment group validate --subscription "$SUB" --resource-group "$RG" \
  --template-file deploy/azure/phase2/main.json \
  --parameters storageName="$STORAGE" planName="$PLAN" appName="$APP" \
    sqlServerName="$SQLSERVER" adminLogin="$ADMIN_LOGIN" adminObjectId="$ADMIN_OBJECT_ID" \
  --only-show-errors --output none
az deployment group what-if --subscription "$SUB" --resource-group "$RG" \
  --template-file deploy/azure/phase2/main.json \
  --parameters storageName="$STORAGE" planName="$PLAN" appName="$APP" \
    sqlServerName="$SQLSERVER" adminLogin="$ADMIN_LOGIN" adminObjectId="$ADMIN_OBJECT_ID" \
  --result-format ResourceIdOnly
# Review resources: no unrelated updates, no new tier, no public openings.
az deployment group create --subscription "$SUB" --resource-group "$RG" \
  --name router-phase2 --template-file deploy/azure/phase2/main.json \
  --parameters storageName="$STORAGE" planName="$PLAN" appName="$APP" \
    sqlServerName="$SQLSERVER" adminLogin="$ADMIN_LOGIN" adminObjectId="$ADMIN_OBJECT_ID" \
  --only-show-errors --output none
az functionapp stop --subscription "$SUB" --resource-group "$RG" --name "$APP"
az functionapp show --subscription "$SUB" --resource-group "$RG" --name "$APP" \
  --query '{state:state,publicNetworkAccess:publicNetworkAccess,outboundIpAddresses:outboundIpAddresses,possibleOutboundIpAddresses:possibleOutboundIpAddresses}'
az deployment group show --subscription "$SUB" --resource-group "$RG" --name router-phase2 --query properties.outputs
```

Outputs contain only SQL FQDN and managed identity principal/client GUIDs, never credentials. Validate state=Stopped and public network Disabled, then SQL free-limit properties and Entra-only administrator. No implicit start or code upload.

## Schema and table grants

First obtain approval for exact migration-client /32 and Function outbound addresses. Current SQL public networking remains Disabled. Do not enable broad Azure-services access. Remove temporary migration rule after use. No migration can run before connectivity is intentionally configured.

Use the current approved SQL administrator as migration operator; no separate permanent migration account or password. Use `src/dotnet/Router.Storage/schema.sql` from this same revision for the dedicated fresh database. Existing databases require schema compatibility review, not merely matching table names.

`render-grants.py` needs the three managed identity **CLIENT IDs**, NOT principal/object IDs. Microsoft's documented CREATE USER WITH SID/TYPE syntax uses client IDs for managed identities. ARM RBAC uses principal IDs; do not interchange them.
https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql#k-create-a-contained-database-user-from-a-microsoft-entra-principal-without-validation

```sh
python3 deploy/azure/phase2/render-grants.py \
  --reader "$READER_CLIENT_ID" --control "$CONTROL_CLIENT_ID" \
  --delivery "$DELIVERY_CLIENT_ID" > /tmp/router-grants.sql
# Requires installed Microsoft ODBC Driver18 and pyodbc. No password/token files.
python3 deploy/azure/phase2/migrate.py --subscription "$SUB" \
  --server "$SQLSERVER.database.windows.net" \
  --schema src/dotnet/Router.Storage/schema.sql --grants /tmp/router-grants.sql
```

Migration takes an access token through the existing az session in memory, never writes/prints it; SQL TLS certificate validation is enabled. No Directory Readers grant is needed by the explicit SID method. The operator must verify IDs before rendering because SQL does not resolve them in Entra.

Permissions: reader SELECT on both registry tables, explicit DENY registry writes; control registry SELECT/INSERT/UPDATE/DELETE and request-log SELECT; delivery receipt SELECT/INSERT, outbox SELECT/INSERT/UPDATE, request-log SELECT/INSERT/DELETE, explicit DENY registry writes. No db_owner/DDL granted to application identities. Add future receipt/outbox purge rights only with a reviewed implementation, not preemptively.

Three connections in one process are logical separation. Application tenant checks remain required; these SQL identities alone are not per-customer row isolation. Validate denied reader writes and control isolation using actual managed identity connections before activation.

## Connection configuration and package

Use SqlClient connection strings:
`Server=tcp:<server>.database.windows.net,1433;Database=router;Authentication=Active Directory Managed Identity;User Id=<identity CLIENT ID>;Encrypt=True;TrustServerCertificate=False;Connect Timeout=30;`

Map RegistryReadConnection to reader, RegistryWriteConnection and LogReadConnection to control, OutboxConnection and LogWriteConnection to delivery. JSON property names are currently CASE-SENSITIVE: use exact PascalCase record fields in RouterRuntime.cs. Never copy the lower-case spelling from conceptual prose into live settings. Do not fabricate tenant/issuer/client/signing-key settings; Keycloak and webhook secrets are still pending.

On Windows with .NET SDK10.0.402 run:
```powershell
./deploy/azure/phase2/package.ps1 -Output "$env:TEMP/router-release-unique"
```
This publishes the actual Functions project, preserves its host.json (do NOT replace with deploy/azure/host.json), includes verified OPA1.9.0 Windows binary and capabilities, excludes local.settings.json, and creates router.zip with host.json at ZIP root. Existing CI tests the OPA binary and app, but this new packaging script still needs Windows execution. No deployment is performed by the script.

Do not use a command that opens SCM/public networking, creates publishing credentials, restarts or starts the app merely to upload the package. SCM access/Entra deployment method must be checked at activation; current no-public-access state intentionally prevents ordinary ZIP deployment. Package may be built while these prerequisites are unresolved. Before activation require Keycloak issuer/JWKS/clients, tenant mapping and approved keys, exact SQL connectivity, successful managed identity permission checks, reviewed publishing route, quota readback, and real hosted authentication/tenant tests. Callback dispatcher and scheduled cleanup remain unverified production work; do not claim full delivery E2E from provisioning.
