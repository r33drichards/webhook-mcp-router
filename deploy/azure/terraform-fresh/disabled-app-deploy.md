# Reviewed closed-app creation workflow

`.github/workflows/azure-router-disabled-app-deploy.yml` is manual, main-only,
protected by the existing `azure-router` environment and infrastructure concurrency
group. It creates one disabled, network-closed app with all 12 foundation resources
unchanged. It does not activate, open firewalls, write secrets/IAM, or delete resources.

The operator must verify the reviewed main commit, approve that exact SHA through
`reviewed_commit`, and set `confirm_disabled_app=true`. The saved-plan checksum
protects the exact locally guarded plan from accidental changes; it does not claim
that a human independently reviewed that binary plan. The approved semantic
contract is enforced immediately before apply. Post-apply requires 13 no-ops.

## Existing identity, no new credential

Use the existing `AZURE_ROUTER_CLIENT_ID`, `AZURE_ROUTER_STATE_ACCOUNT`,
`AZURE_SQL_ADMIN_LOGIN`, `AZURE_SQL_ADMIN_OBJECT_ID` environment variables.
The operator additionally sets the nonsecret `AZURE_ROUTER_PRINCIPAL_ID` from the
existing deployment UAMI's verified principalId, not its clientId. No identity is
created by this workflow. Native bootstrap owns the approved package-container
read/write and three exact UAMI attachment permissions.

GitHub issues a token for audience `api://AzureADTokenExchange`, exact subject
`repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router`.
The subject does not cryptographically bind a workflow filename. Protected main,
environment review and the exact checked-out commit are therefore required.

The helper explicitly runs service-principal `az login --federated-token` in a new
private `AZURE_CONFIG_DIR`. It checks account subscription/tenant/service-principal
client and the ARM token's tenant, client, principal, audience and expiry. Those
local claims checks are identity assertions, not a substitute for Azure validating
GitHub's signature and federated trust. Terraform continues using its own OIDC
backend/provider authentication, not the CLI session. No human CLI session is used.
The runner's installed Azure CLI and gh are used; their binaries are not pinned by
this patch. Checkout and Terraform are pinned as in the reviewed foundation job.

## Pinned package

Only artifact 12615790100 from successful run 40236143640 is accepted. Packaging
commit `dc2c4d51b387a1cbb4f5a86ed8bf7c823a897ab4`, application commit
`b107be2598d3060ccece0c99075f52dff1bb7db5`; wrapper SHA256
`c81803336c2809952ab48a0c821f0ecb3312053244c04234fff4428d6a8d711b`;
inner ZIP SHA256
`2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c`.
Metadata, archive hash, exact archive member names, embedded build manifest and ZIP
hash must all match. Expired/missing artifacts fail closed; no automatic rebuild
or replacement artifact selection. The artifact expires November 1, 2026.

The new helper uses Azure CLI blob operations with explicit `--auth-mode login`;
it does not invoke the older AzureCliCredential uploader from a human session.
Upload uses a block blob, overwrite=false and If-None-Match `*`, then downloads and
hashes the actual bytes. Existing blobs fail closed, even if the filename matches.
No SAS or account key is retrieved. A failed apply may leave the verified package;
no automatic overwrite, deletion, destroy or repeated apply is attempted.

## Runtime limits and cleanup

App creation precedes system-identity runtime grants. The package cannot be assumed
fetchable yet. Key Vault references may be unresolved. Host/queue/package runtime
RBAC, secret contents, SQL schema/grants and networking remain separate steps.
Creating the app does not constitute a working router or live MCP endpoint.

Always-run cleanup removes the isolated CLI credentials, package downloads,
private plans, logs and local Terraform metadata. No raw plan, state, signed URL,
access token or CLI stderr is uploaded or printed. If the runner is forcibly lost,
its ephemeral filesystem lifecycle is the residual cleanup boundary.

Local tests use synthetic metadata, tokens-as-claim-dictionaries, ZIPs and mocked
CLI calls. They do not prove real Azure login, blob authorization, or apply. The
actual protected run is the next integration test.

Official command references:
- https://learn.microsoft.com/en-us/cli/azure/reference-index#az-login
- https://learn.microsoft.com/en-us/cli/azure/storage/blob
- https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-data-operations-cli
