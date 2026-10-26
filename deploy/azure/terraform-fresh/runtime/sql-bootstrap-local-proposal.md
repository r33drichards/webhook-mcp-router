# Local-only administrator bootstrap proposal

Prepared after PR #11's successful DbUp dry run. This is NOT published or approved for live execution. Robert's Mac has not been accessed and its .NET/browser/TDS capabilities are unverified.

## Files and qualification

- `tools/Router.SqlBootstrap`: standalone .NET 10 console helper, Azure.Identity 1.21.0, SqlClient 6.1.4, patched Pkcs 9.0.21.
- `tests/dotnet/Router.SqlBootstrapChecks`: disposable Windows LocalDB rehearsal, not yet run. Production Entra user creation is adapted ONLY in the fixture to WITHOUT LOGIN; schema/grant/transaction checks remain unchanged. This does not prove Azure TYPE E behavior.
- `ci/test-sql-bootstrap-local-contract.py`: source guard passes. It is not compilation or execution evidence.
- Actual local build exits 1 before compilation because .NET cannot create the NuGet-Migrations mutex. New helper has NOT compiled. Separate publication/CI approval is required; earlier PR11 approval does not cover it.

No changes to PR11, main, workflows, Mac or Azure were made in this preparation.

## Helper behavior

`plan <migration-client-guid>` is offline and prints nonsecret reviewed SQL plus SHA256. The migration GUID must be nonzero and distinct from all three fixed runtime client IDs.

`probe <migration-client-guid>` requires `ROUTER_BOOTSTRAP_APPROVED=true`, refuses GitHub Actions and uses AzureCliCredential against the separately approved local Azure CLI session and a TLS-verified connection to the fixed fresh SQL server/router database. It accepts only the current Entra administrator's tenant/object ID and SQL token audience/expiry. It prints only the IPv4 from an expected SQL firewall error40615, not the raw error or token. Unexpected successful connectivity is failure. The operator must validate this address as globally routable before any exact-IP allow rule.

`apply <migration-client-guid> <reviewed-sql-sha256>` checks the same gates and exact SQL hash before any sign-in, then applies a single transaction. It uses a transaction-owned lock matching the migrator. It rejects a nonempty database, non-dbo schema owners, mismatched user SID/type, unexpected direct permissions or explicit role memberships. It creates only missing approved objects; exact pre-migration reruns are idempotent. It verifies the eight explicit grants before commit. Errors are constant/redacted and commit uncertainty is never automatically retried.

The helper has no ARM client or firewall mutation functionality. The native operator owns the separately approved network window and independent cleanup. The SDK obtains the SQL token through its local Azure CLI subprocess and retains it in process memory; the helper never prints it, writes it to a file or sends it to GitHub. The existing Azure CLI maintains its own credential cache; the helper neither copies nor deletes that cache. It performs no login/logout or interactive fallback. Cache cleanup for an operator-created session is a separate Mac task, preserving any pre-existing session.

## Exact identities and SQL permissions

Target subscription38d8d92f-3e84-4ef5-b3da-2788a843aa70 / RG rg-webhook-mcp-router-v2 / SQL sql-webhook-mcp-router-v2-f7076f8e38 / database router. Administrator tenant0e4545fd-804f-4acb-ad41-f955e53645c1, user object9e61efd9-e30d-4bda-93bb-c952234dfe67 (browserjs06@gmail.com). These constants must be independently read-back verified before execution, not inferred from a matching email.

Create a new migration-only UAMI `webhook-mcp-router-v2-f7076f8e38-migrator` in the existing fresh RG. Do not attach it to Functions or grant ARM administration. Its proposed federated credential:

```json
{
  "name": "github-azure-router",
  "properties": {
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router",
    "audiences": ["api://AzureADTokenExchange"]
  }
}
```

This is ongoing identity/trust until explicitly revoked, not a self-expiring grant. Protected environment/main review is the boundary; the subject is not bound to a filename. Keep Keycloak's existing federation unchanged.

Create schemas registry and delivery AUTHORIZATION dbo, no tables. Create contained TYPE E users with explicit binary client SIDs (avoids Graph lookup grants):

| User | Managed identity client ID | Bootstrap grants |
|---|---|---|
| router_reader | 04ae4ee5-f138-4fd0-8b88-c5ae854eced5 | CONNECT only |
| router_control | 17f79290-9166-4206-8792-bda6a541b8b2 | CONNECT only |
| router_delivery | c6255f93-5ebb-4825-b7a1-42325124d72b | CONNECT only |
| router_migrator | New independently verified client ID | CONNECT, CREATE TABLE, VIEW DEFINITION; CONTROL on registry and delivery only |

The migration transaction later gives runtime users the existing exact object-level grants. No runtime DDL, db_owner, ALTER ANY USER, server/master permission or Entra administrator replacement. Schema CONTROL includes data access and permission delegation inside those schemas; it is not a DDL-only grant. These permissions persist after migration unless separately revoked; the current proposal does not silently remove them. LocalDB tests will exercise the permission shape but cannot prove Azure Entra authentication.

## Standard Azure CLI authentication only

Use the official Azure CLI already installed on Robert's Mac, or install it only after explicit Mac approval. The Mac operator verifies the selected account's tenant/user using nonsecret account metadata. If sign-in is needed, it uses the standard Azure CLI login flow with the specified tenant under explicit authorization. Do not print `az account get-access-token`, export a cache, or pass human credentials to GitHub.

The helper uses exactly `AzureCliCredential(new AzureCliCredentialOptions { TenantId=Bootstrap.Tenant, ProcessTimeout=TimeSpan.FromSeconds(30) })`. It requests only the SQL resource token. The token's actual tid, oid, aud and expiry must match the fixed tenant, administrator object and SQL audience before SqlConnection is created. A matching email or default subscription is insufficient. SQL itself authenticates the token; decoding claims here is an additional assertion, not independent signature validation.

No SDK development public application fallback, new custom public-client registration, automatic browser login, DefaultAzureCredential or chained credential is used. Wrong account, missing CLI, expired session or tenant-policy failure stops the helper. This change does not itself authorize a Mac login or new consent.

## Noncircular execution sequence (not yet authorized)

1. Qualify/publish helper through separately approved disposable CI; inspect Mac .NET/browser/direct SQL DNS/TCP only with Mac-specific permission. No production login yet.
2. Native operator creates the migration-only UAMI/FIC and verifies its client/principal IDs; human remains SQL administrator. This alone does not grant SQL access.
3. Review the helper's offline SQL and hash. Native operator verifies SQL initially Disabled/zero firewall rules, then enables with zero rules solely for the administrator's probe. After explicit Mac sign-in consent, use server-observed TDS IPv4 for one exact bootstrap rule. No HTTP-IP guess or broad Azure services rule.
4. Human administrator runs hash-bound helper on Mac; verify four users, two dbo-owned schemas, eight explicit grants, zero user tables. No migration scripts run on Mac.
5. Native operator removes the bootstrap rule WHILE Enabled, then disables PNA in finally. Verify both. On rule-delete failure, still disable PNA and report residual rule; never silently reopen. On closure failure, report immediate unresolved exposure and intervene.
6. Only after bootstrap readback, populate nonsecret migration client/principal/confirmed environment variables. Separately approve/merge/enable the live Actions migration workflow. The migration identity now has a real contained user, so it can execute DbUp without human-token transfer.
7. Actions uses its own observed TDS IP and temporary exact rule, runs one DbUp transaction, removes its rule while Enabled and disables PNA in finally. Native operator watches first execution and handles cleanup after runner loss; no guaranteed firewall TTL.

Network-controller permission delta: existing deployment identity gets firewallRules read/write/delete at the exact fresh SQL server. Existing server write permits PNA edits but ARM does not enforce field-only use. No broad Contributor/IAM grant. Native bootstrap window is a separate specifically approved operator action, not permission for this helper to control ARM.

The minimal remaining live decisions are (a) this precise identity/SQL/network bundle, (b) Mac inspection/sign-in/execution using standard Azure CLI authentication, and (c) reviewed live Actions workflow activation. They can be reviewed together after helper CI passes. No claim is made that the Mac already has connectivity. If the probe fails, stop without switching provider, exporting tokens or expanding firewall scope.

## References

- https://learn.microsoft.com/en-us/dotnet/api/azure.identity.azureclicredentialoptions?view=azure-dotnet
- https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql?view=sql-server-ver17
- https://learn.microsoft.com/en-us/azure/azure-sql/database/connectivity-settings?view=azuresql
