# Proposed C# DbUp migration in GitHub Actions

Status: local draft only. No publication, Azure changes, SQL execution or new credentials. Runtime IAM's six roles/eight assignments are independently verified; those runtime identities receive no DDL rights.

## Implementation

`tools/Router.Migrator` is a standalone .NET 10 executable using DbUp SQL Server 7.2.0, Microsoft.Data.SqlClient 6.1.4 and Azure.Identity 1.21.0. It is not referenced by Functions. It embeds the unchanged baseline and destination schema scripts between a fresh-database guard, exact runtime object grants and an eight-table verification. DbUp uses one transaction, transaction-owned application lock, suppressed SQL/error logging and no journal table. This intentionally supports only the first empty-database migration; subsequent migrations need a separately reviewed journal/version design. Never retry an uncertain migration automatically: reconcile the database first.

The proposed workflow builds and runs real Windows LocalDB transaction tests before opening SQL. The migrator requests GitHub OIDC explicitly, exchanges it as a separate managed identity for an Azure SQL token, validates identity/audience claims and connects with certificate validation. No password or Function-startup migration is used.

## Exact proposed bootstrap and permissions

1. Create a migration-only UAMI `webhook-mcp-router-v2-f7076f8e38-migrator`, not attached to the Function. Federate issuer `https://token.actions.githubusercontent.com`, subject `repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router`, audience `api://AzureADTokenExchange`. Preserve the repository OIDC template and existing Keycloak trust. The protected main-only environment binds the job, not its filename cryptographically. Any approved job in that environment is within this trust boundary.
2. Set nonsecret environment variables `AZURE_ROUTER_MIGRATION_CLIENT_ID` and `AZURE_ROUTER_MIGRATION_PRINCIPAL_ID`. Give this identity no ARM administration roles. A human administrator must first create its contained user in the existing fresh `router` database. The pipeline cannot create its own SQL access.
3. In one separately reviewed administrator bootstrap, precreate `registry` and `delivery` schemas owned by dbo, and the three existing runtime users with their verified managed-identity client IDs and CONNECT. Create `router_migrator` with the new verified client SID/TYPE E and CONNECT. Candidate migration permissions: database CREATE TABLE and VIEW DEFINITION, plus CONTROL only on these two schemas so it can create objects and issue the exact object GRANT/DENY statements. CONTROL includes data access and permission delegation within those schemas; it is not merely DDL. Do not grant db_owner, ALTER ANY USER, server/master access or runtime DDL. Validate these permissions on SQL before treating them as qualified. The initial human-admin connection and its temporary network window still need an explicit operator procedure/approval; this is a real bootstrap dependency, not solved by OIDC alone.
4. The existing deployment identity controls only the network window, separate from the SQL migration identity. Proposed additional actions are `Microsoft.Sql/servers/firewallRules/read`, `/write` and `/delete` on this exact fresh SQL server. It already has server read/write through foundation rights. ARM server write cannot be restricted by field to publicNetworkAccess, and server-scoped firewall rights cover all rules; reviewed code/protected environment enforce the narrower behavior. No broad Contributor, IAM writes, SQL password or 0.0.0.0 rule.
5. Set `AZURE_ROUTER_MIGRATION_BOOTSTRAP_CONFIRMED=true` only after verifying the contained users, permissions and approved network role. This flag is an operator assertion, not independent proof.

Target: subscription `38d8d92f-3e84-4ef5-b3da-2788a843aa70`, RG `rg-webhook-mcp-router-v2`, server `sql-webhook-mcp-router-v2-f7076f8e38`, database `router`. No old resource or shared service is touched.

## Network window and recovery

The job first requires publicNetworkAccess Disabled and zero server firewall rules. It records cleanup intent before enabling the public endpoint with zero allowed addresses. A TLS-validated connection to the exact SQL hostname must return SQL error 40615 with its observed client IPv4. That address is validated as globally routable, then used as both start/end of the single rule `router-migration-<run>-<attempt>`. There is no HTTP IP-service fallback, IP-range expansion or default Azure-services bypass. If SQL does not supply this evidence, stop and close the endpoint. Actual Azure routing, propagation and this diagnostic have not yet been exercised.

Normal cleanup removes only this run's rule while public access is still Enabled, verifies removal, then disables public access in finally and verifies closure. Microsoft documents that firewall changes, including deletion, are blocked when public access is Disabled. If deletion or its readback fails, finally still attempts closure, and the job fails visibly. A residual rule behind Disabled access is containment, not complete cleanup. If closing access also fails, closure is unverified and the operator must intervene immediately.

Independent manual cleanup on a new runner never silently reopens access. If access is already Disabled with a residual owned rule, it reports incomplete cleanup and leaves access Disabled. Removing that residual requires a separately approved short reopening window: first inspect every existing rule, confirm the exact owned rule and its address, enable, delete, then disable in finally. Reopening temporarily makes the old allowed IP effective; do not assume it still belongs to this runner. Do not use this route without explicit review. No rule TTL exists in this design.

A native operator must watch the first run. The 20-minute timeout and always() do not guarantee cleanup after runner loss or cancellation. Shared infrastructure concurrency covers normal workflows, not external administrator changes. Unrelated rules are never deleted.

## One-time administrator bootstrap route

The new OIDC identity cannot grant itself SQL access. The native environment currently cannot resolve/connect to SQL, and no functional administrator route has been demonstrated. Do not copy its Azure token/cache into GitHub or put a human token, device code, password or refresh token in Actions logs/artifacts/secrets.

The preferred concrete bootstrap is a small C# operator command on an administrator-controlled workstation with working direct SQL DNS/TCP, using Azure.Identity InteractiveBrowserCredential for the existing approved Entra administrator. It requests the SQL token in-process, verifies tenant and administrator object ID, and uses Microsoft.Data.SqlClient with certificate validation. No credential transfer to Actions is needed. The exact bootstrap SQL creates the two dbo-owned schemas and four contained users, grants CONNECT, and grants the migration-only permissions described above. It must verify any existing name/SID before mutation and run transactionally. This operator command is a proposed additional deliverable, not implemented or tested yet.

The administrator workstation needs its own reviewed temporary exact TDS-IP firewall window and closure verification, using the same documented ordering. Its observed egress must not be guessed from the blocked native environment. A working administrator workstation/session must be identified before approval to execute; absent one, bootstrap remains blocked. A GitHub-hosted human login would instead transmit administrator authority to a runner and requires a separately reviewed private consent/credential-handling path; none exists here and it is not part of this draft. Do not substitute temporary Entra administrator replacement or broad migration-identity privileges.


No new paid compute, private endpoint, NAT or runtime plan is proposed. Existing SQL free-limit AutoPause and the combined $10 alert budget stay unchanged. Alerts are not a hard cap.

## Validation evidence and remaining gates

- Thirteen offline network-window cases passed, covering exact IP handling, unrelated-rule refusal/preservation and delete-before-disable ordering, failure containment and residual-rule refusal.
- Proposed workflow parses; job permissions are contents:read/id-token:write only.
- Actual local build exited 1 before compilation: .NET CLI could not create the `NuGet-Migrations` named mutex. This is an environment/tool startup failure, not a successful compile or dependency validation.
- Windows LocalDB tests are prepared for rollback, eight-table commit/no journal and nonempty rejection. They have not run. They use integrated local auth and synthetic grants, not Azure Entra principals.
- Actual OIDC SQL authentication, least-permission bootstrap, Azure firewall probe and migration remain untested. Publication/CI approval must precede qualification; live identity, SQL bootstrap and network access require the precise bundle above.
- Optional MCP backplane review remains issue #10 and is not included in this migration change set. The Function remains disabled and network-closed.

## Primary references

- [DbUp transactions](https://dbup.readthedocs.io/en/latest/more-info/transactions/) and [journaling](https://dbup.readthedocs.io/en/latest/more-info/journaling/).
- [Azure SQL GitHub Actions connectivity/authentication](https://learn.microsoft.com/en-us/azure/azure-sql/database/connect-github-actions-sql-db?view=azuresql).
- [SQL connection errors including 40615](https://learn.microsoft.com/en-us/azure/azure-sql/database/troubleshoot-common-errors-issues?view=azuresql).
- [CREATE TABLE permission requirements](https://learn.microsoft.com/en-us/sql/relational-databases/tables/create-tables-database-engine?view=sql-server-ver17).
- [Managed identities and explicit SQL SID/TYPE](https://learn.microsoft.com/en-us/azure/azure-sql/database/authentication-azure-ad-user-assigned-managed-identity?view=azuresql).

- [Azure SQL connectivity settings: firewall edits are rejected while public access is disabled](https://learn.microsoft.com/en-us/azure/azure-sql/database/connectivity-settings?view=azuresql).
