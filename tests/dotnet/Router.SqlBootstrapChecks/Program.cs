using System.Diagnostics;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Router.SqlBootstrap;

var migrationId=new Guid("11111111-2222-4333-8444-555555555555");
var production=Bootstrap.Build(migrationId);
if(Bootstrap.Sid(Bootstrap.Reader)!="0xe54eae0438f1d04f8b88c5ae854eced5")throw new Exception("SID_ENDIANNESS");
if(Regex.Matches(production,"TYPE=E;").Count!=4 || production.Contains("FROM EXTERNAL PROVIDER") || production.Contains("db_owner"))throw new Exception("PRODUCTION_CONTRACT");
foreach(var bad in new[]{Guid.Empty,Bootstrap.Reader,Bootstrap.Control,Bootstrap.Delivery}){
 try{Bootstrap.Build(bad);throw new Exception("BAD_ID_ACCEPTED");}catch(ArgumentException){}
}
Console.WriteLine("PASS exact external-user SQL shape, SID encoding and distinct migration identity");
if(!OperatingSystem.IsWindows())throw new InvalidOperationException("WINDOWS_LOCALDB_REQUIRED");
// LocalDB cannot authenticate Entra users. Only fixture user creation/SID checks
// are adapted; all schema, permission, transaction and fail-closed SQL is unchanged.
var fixture=Regex.Replace(production,@"sid<>0x[0-9a-f]{32} OR type<>'E'","type<>'S'");
fixture=Regex.Replace(fixture,@"WITH SID=0x[0-9a-f]{32}, TYPE=E;","WITHOUT LOGIN;");
var instance="RouterBootstrap"+Guid.NewGuid().ToString("N")[..10];
void Local(string verb){using var p=Process.Start(new ProcessStartInfo("SqlLocalDB",$"{verb} {instance}"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true})!;var o=p.StandardOutput.ReadToEndAsync();var e=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(60000)){p.Kill(true);throw new Exception("LOCALDB_TIMEOUT");}Task.WaitAll(o,e);if(p.ExitCode!=0)throw new Exception("LOCALDB_FAILED");}
var cs=$@"Server=(localdb)\{instance};Integrated Security=true;Encrypt=false;Pooling=False;Initial Catalog=";
void Sql(string db,string sql){using var c=new SqlConnection(cs+db);c.Open();using var cmd=new SqlCommand(sql,c);cmd.ExecuteNonQuery();}
int Count(string sql){using var c=new SqlConnection(cs+"router");c.Open();using var cmd=new SqlCommand(sql,c);return (int)cmd.ExecuteScalar();}
async Task Apply(string sql){using var c=new SqlConnection(cs+"router");await Bootstrap.Execute(c,sql);}
async Task MustFail(string sql){try{await Apply(sql);}catch(SqlException){return;}throw new Exception("EXPECTED_REJECTION");}
bool created=false;
try{
 Local("create");created=true;Local("start");Sql("master","CREATE DATABASE router");
 await MustFail(fixture+"\nTHROW 51000,'SYNTHETIC_FAILURE',1;");
 if(Count("SELECT COUNT(*) FROM sys.schemas WHERE name IN ('registry','delivery')")!=0 || Count("SELECT COUNT(*) FROM sys.database_principals WHERE name LIKE 'router[_]%'")!=0)throw new Exception("ROLLBACK_FAILED");
 Console.WriteLine("PASS rollback removes schemas, users and grants after injected failure");
 await Apply(fixture);
 if(Count("SELECT COUNT(*) FROM sys.database_principals WHERE name IN ('router_reader','router_control','router_delivery','router_migrator')")!=4 || Count("SELECT COUNT(*) FROM sys.schemas WHERE name IN ('registry','delivery') AND principal_id=USER_ID('dbo')")!=2 || Count("SELECT COUNT(*) FROM sys.database_permissions WHERE grantee_principal_id IN (SELECT principal_id FROM sys.database_principals WHERE name LIKE 'router[_]%')")!=8)throw new Exception("EXACT_BOOTSTRAP_FAILED");
 await Apply(fixture);Console.WriteLine("PASS four fixture users, two dbo schemas, eight grants and idempotent bootstrap rerun");
 Sql("router","EXECUTE AS USER='router_migrator'; CREATE TABLE registry.permission_probe(Id int); GRANT SELECT ON OBJECT::registry.permission_probe TO router_reader; DROP TABLE registry.permission_probe; REVERT;");
 if(Count("EXECUTE AS USER='router_migrator'; SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','ALTER ANY USER'); REVERT;")!=0)throw new Exception("UNEXPECTED_USER_ADMIN");
 Console.WriteLine("PASS schema-scoped migration create/grant works without ALTER ANY USER");
 Sql("router","ALTER ROLE db_owner ADD MEMBER router_migrator;");await MustFail(fixture);Sql("router","ALTER ROLE db_owner DROP MEMBER router_migrator;");
 Sql("router","GRANT CREATE VIEW TO router_migrator;");await MustFail(fixture);Sql("router","REVOKE CREATE VIEW FROM router_migrator;");
 Console.WriteLine("PASS unexpected role membership and extra direct grant rejected");
 Sql("router","CREATE TABLE dbo.keep_me(Id int);");await MustFail(fixture);
 if(Count("SELECT COUNT(*) FROM sys.tables WHERE name='keep_me'")!=1)throw new Exception("DATA_CHANGED");
 Console.WriteLine("PASS nonempty database rejected without removing existing table");
 Console.WriteLine("LIMIT: fixture WITHOUT LOGIN users; Azure TYPE E creation, real interactive auth and network connectivity untested");
}finally{if(created){try{Local("stop");}finally{Local("delete");}}}
