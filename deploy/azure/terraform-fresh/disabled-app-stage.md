# Next stage: disabled Function app, not runtime activation

Foundation read-only run40264935233 at7ceb2e141cd2cde3311e5ec3ceb097117c03462c verified twelve no-op resources. Existing old runtime/control-plane resources remain protected. Combined monthly router budget remains$10 (alerts, not a cap).

## Existing usable package

Successful build40236143640 (packaging commit dc2c4d51b387a1cbb4f5a86ed8bf7c823a897ab4) produced artifact12615790100, router-windows-b107be25-40236143640, unexpired until2026-11-01T21:39:50Z.

- Application commit b107be2598d3060ccece0c99075f52dff1bb7db5.
- Inner router.zip SHA256: 2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c.
- GitHub artifact-wrapper digest: c81803336c2809952ab48a0c821f0ecb3312053244c04234fff4428d6a8d711b. Do not confuse this with the inner ZIP digest.
- Artifact URL: https://github.com/r33drichards/webhook-mcp-router/actions/runs/40236143640/artifacts/12615790100
- SDK10.0.402, OPA1.9.0. Extracted-package Functions host, packaged OPA and controlled HTTPS tests passed. Production managed-identity/Keycloak/SQL connectivity was not exercised.
- GitHub comparison b107be25...7ceb2e14 shows no src/dotnet or policies changes; only tests/dotnet/Router.HostChecks/Program.cs changed in those source/test areas. Thus no new application build is required for this stage. Recheck comparison if application code changes.

Retrieve through authorized artifact access, verify wrapper and inner ZIP hashes and build.json before any upload. Nothing has been downloaded or uploaded by this preparation. Use the protected OIDC workflow described in disabled-app-deploy.md for conditional no-overwrite upload and download/hash verification; do not run an uploader from a human CLI session. URL must be https://whmcprv2f7076f8e38.blob.core.windows.net/router-packages/2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c.zip. No SAS, storage keys or SCM publication. Existing-object conflict fails closed; never silently overwrite.

## Concrete closed stage

The prepared azure-router-disabled-app-plan.yml is manual/main/protected azure-router, PLAN ONLY. Input package_sha256 is the inner ZIP digest above. It sets runtime_ready=true, app_enabled=false, public_http_enabled=false and dispatch_enabled=false; ingress and SQL address lists stay empty.

The stage guard requires exactly twelve unchanged foundation resources plus one app creation/no-op (thirteen total), exact fresh identities, exact private package URI/hash, system-assigned package/host/queue configuration, and all three Key Vault reference names. No foundation updates, app updates, activation, IAM, firewall or deletion are accepted. Existing cost/security guard still applies. Thirty-four stage fixtures pass locally; no real app plan has run.

Creating the app produces its system principal, so package/host/queue runtime grants follow creation. Do not claim a functioning package mount before those grants. The app uses the existing control UAMI for Key Vault references. Unresolved references may remain literal reference strings; the app stays disabled and closed. No real JSON secrets, ingress key, dip client or SQL migration are required merely to create this inert shell. This is not readiness for starting it.

## Exact access delta to review

Existing new-RG resource role already includes Microsoft.Web/sites read/write and config read/write. No broader role is needed for app resource CRUD.

Before creating an app attached to existing UAMIs, assign the deployment identity Microsoft.ManagedIdentity/userAssignedIdentities/assign/action at ONLY these resources under rg-webhook-mcp-router-v2:
- webhook-mcp-router-v2-f7076f8e38-control
- webhook-mcp-router-v2-f7076f8e38-delivery
- webhook-mcp-router-v2-f7076f8e38-registry-reader

For uploading the package, grant deployment identity Blob read/write only at whmcprv2f7076f8e38/blobServices/default/containers/router-packages; no delete, account keys, delegation key or other container access. Existing state role is separate. The approved uploader is the isolated protected GitHub workflow using the existing deployment identity, not a native human CLI session.

After app creation, proposed system-principal runtime roles are package Blob read only; host containers read/write and blobs read/write/delete at azure-webjobs-hosts and azure-webjobs-secrets only; dispatch queue read and messages read/process/write/add at router-dispatch; poison messages add at router-dispatch-poison. Native operator must approve/assign exact bindings after obtaining the new principal; no automatic broad Blob Owner fallback. Local Azurite tests do not qualify Azure RBAC.

No new permission/resource apply is performed by this preparation. A subsequent reviewed saved-plan apply is needed to create the disabled app; the foundation-only apply deliberately cannot create it.

## Runtime configuration and activation dependencies (later)

All secrets remain operator-created in kv-whmcprv2-f7076f8e38; not Terraform values, source files, chat or CI logs. Control UAMI needs get only on router-auth, router-tenants and router-delivery-keys. Native bootstrap created the vault, not runtime grants/values.

ROUTER_AUTH_JSON: Issuer https://keycloak-production-295b.up.railway.app/realms/webhook-router; Jwks issuer+/protocol/openid-connect/certs; Audience must equal the reviewed router audience configured on actual application client tokens (do not reuse management federation audience implicitly). Clients entries require exact ClientId, service-account Subject, TenantId mcp-js and permitted Scopes. The Terraform management client is not a runtime/dip client. Runtime client creation/secret issuance remains a separate exact authorization.

ROUTER_TENANTS_JSON: one tenant mcp-js/source mcp-js-github, GitHubRepositoryId961207108, GenericRouting=true, GitHubPullRequest=null (all event types), DestinationBindings=[] initially. IngressKeyBase64 requires an approved24–64byte key. Generic routing does not use Callback/CallbackKeyBase64; they can remain empty. Five SQL connections use Encrypt=True;TrustServerCertificate=False;Authentication=Active Directory Managed Identity;User Id=<NEW UAMI CLIENT ID>;Server=tcp:sql-webhook-mcp-router-v2-f7076f8e38.database.windows.net,1433;Database=router. RegistryRead uses reader; RegistryWrite and LogRead use control; Outbox and LogWrite use delivery. Obtain fresh IDs from verified Terraform output/ARM readback, never old IDs.

ROUTER_DELIVERY_KEYS_JSON: tenant→approved alias→base64 key map. Empty {"mcp-js":{}} is deny-by-default staging, not delivery readiness. No destination or callback key is created here.

SQL migration: use existing operator login as the approved Entra SQL administrator. Run render-grants.py --generic with NEW client IDs, then migrate.py --generic against the exact new server/database and pinned schemas. Migration is fresh-only and transactional; LocalDB rollback/repeat-rejection passed. Azure Entra SID grants remain untested. SQL remains public-disabled; migration needs separately approved exact temporary operator egress rule, later exact app outbound-IP rules, and removal of temporary rule. GitHub-hosted runner egress is not a guaranteed stable address. No Azure-services-wide0.0.0.0 rule, password administrator or automatic paid-SQL fallback.

Only after package/host/queue permissions, secret references, client mapping, SQL schema/grants and approved network tests pass should declarative app/dispatch/ingress activation be considered. Old runtime deletion still waits for replacement acceptance and explicit data/dependency inspection; never delete the old RG containing state/deployment identity.

Guard coverage: 34 disabled-app fixtures plus 57 foundation/diagnostic regressions. The deployment workflow has separate offline identity, artifact and transport tests; no live Azure apply is implied.
