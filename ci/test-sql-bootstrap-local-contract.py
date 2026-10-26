"""Local source guard, not a C# compilation or database integration test."""
from pathlib import Path
import uuid
root=Path(__file__).resolve().parents[1]
source=(root/'tools/Router.SqlBootstrap/Bootstrap.cs').read_text()
cli=(root/'tools/Router.SqlBootstrap/Program.cs').read_text()
checks=(root/'tests/dotnet/Router.SqlBootstrapChecks/Program.cs').read_text()
assert uuid.UUID('04ae4ee5-f138-4fd0-8b88-c5ae854eced5').bytes_le.hex()=='e54eae0438f1d04f8b88c5ae854eced5'
for required in ['LockOwner=\'Transaction\'','NONEMPTY_DATABASE_REQUIRES_REVIEW','SCHEMA_OWNER_MISMATCH','PRINCIPAL_MISMATCH','EXISTING_ROLE_MEMBERSHIP_DENIED','EXISTING_PERMISSION_DENIED','GRANT_READBACK_FAILED','UNEXPECTED_GRANT','connection.BeginTransaction()','transaction.Commit()','transaction.Rollback()']:
 assert required in source,required
assert 'ALTER ANY USER' not in source and 'db_owner' not in source
assert source.count('GRANT CONTROL ON SCHEMA::')==2
for required in ['new AzureCliCredential(new AzureCliCredentialOptions','Bootstrap.Administrator','Bootstrap.Tenant','TrustServerCertificate=False','GITHUB_ACTIONS','ROUTER_BOOTSTRAP_APPROVED','args[2]==hash']:
 assert required in cli,required
for forbidden in ['DefaultAzureCredential','InteractiveBrowserCredential','ROUTER_BOOTSTRAP_ALLOW_SDK_DEV_CLIENT','DeviceCodeCredential','ChainedTokenCredential','TokenCachePersistenceOptions','management.azure.com','Console.WriteLine(token','Console.WriteLine(e.Message']:
 assert forbidden not in cli,forbidden
assert cli.count('new AzureCliCredential(')==1
assert 'TenantId=Bootstrap.Tenant,ProcessTimeout=TimeSpan.FromSeconds(30)' in cli
assert cli.index('args[2]==hash') < cli.index('new AzureCliCredential(') < cli.index('GetTokenAsync') < cli.index('c.GetProperty("oid")') < cli.index('new SqlConnection(')
assert 'SYNTHETIC_FAILURE' in checks and 'WITHOUT LOGIN' in checks
print('PASS local bootstrap source guard; NOT compiled or SQL-tested')
