using System.Diagnostics;
using DbUp.Engine;
using Microsoft.Data.SqlClient;
using Router.Migrator;
if(!OperatingSystem.IsWindows())throw new InvalidOperationException("ISOLATED_WINDOWS_LOCALDB_REQUIRED");
string instance="RouterDbUp"+Guid.NewGuid().ToString("N")[..12];
void LocalDb(string command) {using var p=Process.Start(new ProcessStartInfo("SqlLocalDB",$"{command} {instance}"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true})!;var stdout=p.StandardOutput.ReadToEndAsync();var stderr=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(60000)){p.Kill(entireProcessTree:true);throw new InvalidOperationException("LOCALDB_TIMEOUT");}Task.WaitAll(stdout,stderr);if(p.ExitCode!=0)throw new InvalidOperationException("LOCALDB_OPERATION_FAILED");}
string cs=$@"Server=(localdb)\{instance};Integrated Security=true;Encrypt=false;Pooling=False;Initial Catalog=";
void Sql(string db,string text){using var c=new SqlConnection(cs+db);c.Open();using var cmd=new SqlCommand(text,c);cmd.ExecuteNonQuery();}
int Tables(){using var c=new SqlConnection(cs+"router");c.Open();using var cmd=new SqlCommand("SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0",c);return (int)cmd.ExecuteScalar();}
bool created=false;
try {
 LocalDb("create");created=true;LocalDb("start");Sql("master","CREATE DATABASE router");
 Sql("router","CREATE SCHEMA registry;");Sql("router","CREATE SCHEMA delivery;");Sql("router","CREATE USER fixture_reader WITHOUT LOGIN;");
 var scripts=Migration.Scripts();
 SqlScript[] WithGrant(string grant)=>scripts.Select(s=>s.Name=="030-runtime-grants.sql"?new SqlScript(s.Name,grant):s).ToArray();
 var result=Migration.Run(()=>new SqlConnection(cs+"router"),WithGrant("THROW 51000,'SYNTHETIC_GRANT_FAILURE',1;"));
 if(result.Successful||Tables()!=0)throw new Exception("ROLLBACK_FAILED");Console.WriteLine("PASS DbUp single transaction rolls both schemas back on grant failure");
 result=Migration.Run(()=>new SqlConnection(cs+"router"),WithGrant("GRANT SELECT ON OBJECT::registry.Destinations TO fixture_reader;"));
 if(!result.Successful||Tables()!=8)throw new Exception("MIGRATION_FAILED");Console.WriteLine("PASS DbUp commits eight tables and synthetic grant without journal table");
 using(var c=new SqlConnection(cs+"router")){c.Open();using var cmd=new SqlCommand("SELECT COUNT(*) FROM sys.database_permissions WHERE grantee_principal_id=USER_ID('fixture_reader') AND major_id=OBJECT_ID('registry.Destinations') AND permission_name='SELECT' AND state='G'",c);if((int)cmd.ExecuteScalar()!=1)throw new Exception("GRANT_NOT_COMMITTED");}
 Console.WriteLine("PASS exact synthetic object grant committed");
 result=Migration.Run(()=>new SqlConnection(cs+"router"),WithGrant("SELECT 1;"));
 if(result.Successful||Tables()!=8)throw new Exception("NONEMPTY_GUARD_FAILED");Console.WriteLine("PASS DbUp refuses nonempty database without changing tables");
 Console.WriteLine("LIMIT: local integrated auth and synthetic grant; Azure OIDC, runtime Entra users and least-DDL grant bootstrap untested");
}finally{if(created){try{LocalDb("stop");}finally{LocalDb("delete");}}}
