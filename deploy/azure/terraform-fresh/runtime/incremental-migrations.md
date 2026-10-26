# Recurring migrations: local proposal, not published or executed

The persistent migration UAMI/OIDC trust already supports recurring authentication. This change addresses the separate application limitation: the merged DbUp implementation uses NullJournal and refuses every nonempty database. No live migration has occurred. Azure authentication is currently blocked by AADSTS530035; this proposal does not change security defaults or try another identity.

## Proposed durable contract

- Add `registry.SchemaVersions` under the existing migrator schema CONTROL permission. Columns: ScriptName (case-sensitive primary key), ContentHash (SHA-256), AppliedUtc (UTC). Runtime identities receive no journal permissions.
- Before DbUp selects pending scripts, acquire the same transaction-owned application lock used by bootstrap, with zero wait. Hold it through journal selection, all pending scripts, journal inserts and commit. A concurrent job fails closed rather than selecting stale pending work.
- First application requires no user tables when no journal exists. Creation of the journal and initial schema commits together. Existing unjournaled data is never automatically adopted, marked executed or wiped.
- Initial versions remain 010-baseline, 020-destinations, 030-runtime-grants and 040-verify. The baseline verifies eight application tables plus the journal. Initial scripts run once, not on every deployment.
- New embedded version files use ordered three-digit names (e.g. 050-add-index.sql); resource discovery validates names and allows only append-only history. New versions after the baseline are selected automatically.
- Applied journal rows must be an exact prefix of the supplied manifest, with matching hashes. Removed/edited applied scripts, incomplete baseline history and backdated versions fail. Hashes normalize CRLF to LF so Windows versus Mac checkout endings do not create false drift.
- An unchanged manifest is a successful no-op, with zero scripts executed. Each pending batch is a single DbUp transaction; failure rolls back both its DDL/data changes and journal entries. Previously committed migrations remain intact.
- Later migrations can add tables. The exact nine-table check is a versioned initial assertion, not an always-run upper bound. Preflight continues to require the baseline tables on every journaled run; a future intentional baseline-table rename/drop requires an explicit reviewed change to that invariant.
- The bootstrap helper remains one-time only and still refuses a nonempty database. Recurring migrations use the already-created migrator user, never human credentials or Function startup.

This uses DbUp's documented IJournal extension with its managed command factory and WithTransaction. Upstream source confirms journal selection occurs inside OperationStarting, before script execution, and managed-command exceptions mark the single transaction for rollback. The custom journal adds lock-before-read and content-hash checks that a name-only stock journal would not provide.

## Prepared integration regression suite

Start with the new regression: after a successful baseline, the identical manifest must succeed with zero executed scripts. The former NullJournal implementation fails that behavioral contract. The attempted local execution failed before compilation on the .NET NuGet-Migrations mutex; no executed red test is claimed.

The revised Windows LocalDB test prepares:
1. Nonempty unjournaled database refusal without adoption or mutation.
2. Forced initial grant failure rolling back application tables and journal creation.
3. First apply: eight application tables, one journal, four version rows and exact synthetic grant.
4. Unchanged rerun: zero scripts, unchanged journal and preserved sentinel application data.
5. Append a table/data migration: executes exactly once and is journaled.
6. Changed applied script and missing version rejection without state changes; portable newline fingerprint.
7. Failed later migration and failed multi-script batch: new DDL and all new history roll back.
8. Two actual overlapping migrator calls: a synthetic gate holds the winner after it acquires the migration lock; loser receives MIGRATION_LOCK_UNAVAILABLE, winner commits once, later rerun does nothing.

LocalDB fixtures substitute only the runtime Entra grant script with a synthetic object grant. They do not qualify Azure Entra login or network behavior. No new live rights are proposed.

## Actual validation / limits

- Existing five workflow path-filter cases and thirteen offline firewall-window cases pass locally after the edit.
- No new C# integration result exists yet. Local CLI exits before compile on NuGet-Migrations mutex.
- One official SDK container attempt (`mcr.microsoft.com/dotnet/sdk:10.0.402`) failed downloading image configuration/layers with Forbidden; no alternative download route was attempted.
- Source/API review uses DbUp 6.1.1 core (dependency of SQL Server package 7.2.0): IJournal, UpgradeEngine.PerformUpgrade, DatabaseConnectionManager and SingleTransactionStrategy. Compile/runtime verification still requires authorized Windows CI publication.

## Scope and approval still needed

Local changes only: migrator/journal/preflight/baseline verification, integration tests, documentation and workflow step wording. Persistent OIDC identity, exact-server firewall rights, per-run IP rule and cleanup remain unchanged. Public SQL access is not made permanently open. The combined $10 budget, stopped Function and existing infrastructure remain unchanged.

Request approval to publish this narrow change as a PR and execute disposable Windows tests, followed by independent review before merge. Do not dispatch the live migration until the new journal implementation passes review/CI and the separate administrator bootstrap/authentication gates are satisfied. No weakening of AADSTS530035/security defaults is included.

Sources: https://dbup.readthedocs.io/en/latest/more-info/journaling/ ; https://dbup.readthedocs.io/en/latest/more-info/transactions/ ; https://github.com/DbUp/DbUp/tree/6.1.1/src/dbup-core
