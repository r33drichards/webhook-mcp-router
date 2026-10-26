using System.Diagnostics;
using DbUp.Engine;
using Microsoft.Data.SqlClient;
using Router.Migrator;
// No wall-clock delays or SQL calls in retry-policy qualification.
if(!ConnectionWarmup.IsResumeOnly([40613]) || ConnectionWarmup.IsResumeOnly([]) || ConnectionWarmup.IsResumeOnly([40613,18456]) || ConnectionWarmup.IsResumeOnly([40615]))throw new Exception("RESUME_CLASSIFIER");
foreach(var scenario in new[]{"success","resume","exhausted","other","cancelled"}) {
 int attempts=0,waits=0;bool failed=false;
 using var cancel=new CancellationTokenSource();if(scenario=="cancelled")cancel.Cancel();
 try {await ConnectionWarmup.RetryAsync(ct=>{attempts++;if(scenario=="other")throw new ArgumentException("synthetic");if(scenario=="exhausted" || scenario=="resume" && attempts<3)throw new InvalidOperationException("synthetic");return Task.CompletedTask;},e=>e is InvalidOperationException,cancel.Token,(span,ct)=>{if(span!=TimeSpan.FromSeconds(10))throw new Exception("DELAY_POLICY");waits++;return Task.CompletedTask;});}
 catch(Exception e) when(e is InvalidOperationException or ArgumentException or OperationCanceledException){failed=true;}
 if(failed!=(scenario is "exhausted" or "other" or "cancelled") || attempts!=(scenario=="exhausted"?6:scenario=="resume"?3:scenario=="cancelled"?0:1) || waits!=(scenario=="exhausted"?5:scenario=="resume"?2:0))throw new Exception("BOUNDED_WARMUP_POLICY");
}
Console.WriteLine("PASS connection-only 40613 classifier, success/resume/exhaustion/nonretry/cancellation; no transaction replay");
if(!OperatingSystem.IsWindows())throw new InvalidOperationException("ISOLATED_WINDOWS_LOCALDB_REQUIRED");
string instance="RouterDbUp"+Guid.NewGuid().ToString("N")[..12];
void LocalDb(string command){using var p=Process.Start(new ProcessStartInfo("SqlLocalDB",$"{command} {instance}"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true})!;var o=p.StandardOutput.ReadToEndAsync();var e=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(60000)){p.Kill(true);throw new Exception("LOCALDB_TIMEOUT");}Task.WaitAll(o,e);if(p.ExitCode!=0)throw new Exception("LOCALDB_OPERATION_FAILED");}
string cs=$@"Server=(localdb)\{instance};Integrated Security=true;Encrypt=false;Pooling=False;Initial Catalog=";
void Sql(string db,string text){using var c=new SqlConnection(cs+db);c.Open();using var cmd=new SqlCommand(text,c);cmd.ExecuteNonQuery();}
int Scalar(string text){using var c=new SqlConnection(cs+"router");c.Open();using var cmd=new SqlCommand(text,c);return (int)cmd.ExecuteScalar();}
int Tables()=>Scalar("SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0");
int History()=>Scalar("SELECT COUNT(*) FROM registry.SchemaVersions");
DatabaseUpgradeResult Run(SqlScript[] scripts)=>Migration.Run(()=>new SqlConnection(cs+"router"),scripts);
void Require(bool ok,string message){if(!ok)throw new Exception(message);}
void SqlFailure(DatabaseUpgradeResult result,string code)=>Require(!result.Successful && result.Error is SqlException e && e.Number==51000 && e.Message.Contains(code,StringComparison.Ordinal),"WRONG_FAILURE_"+code);
void HistoryFailure(DatabaseUpgradeResult result)=>Require(!result.Successful && result.Error is InvalidOperationException,"HISTORY_FAILURE_REQUIRED");
bool created=false;
try {
 LocalDb("create");created=true;LocalDb("start");Sql("master","CREATE DATABASE router");
 Sql("router","CREATE SCHEMA registry;");Sql("router","CREATE SCHEMA delivery;");Sql("router","CREATE USER fixture_reader WITHOUT LOGIN;");
 var scripts=Migration.Scripts();
 SqlScript[] Grant(string grant)=>scripts.Select(s=>s.Name=="030-runtime-grants.sql"?new SqlScript(s.Name,grant):s).ToArray();
 var baseline=Grant("GRANT SELECT ON OBJECT::registry.Destinations TO fixture_reader;");
 Sql("router","CREATE TABLE dbo.preexisting(Id int);");
 SqlFailure(Run(baseline),"UNJOURNALED_DATABASE_REQUIRES_REVIEW");
 Require(Tables()==1 && Scalar("SELECT COUNT(*) FROM sys.tables WHERE name='SchemaVersions'")==0,"UNJOURNALED_STATE_CHANGED");Sql("router","DROP TABLE dbo.preexisting;");
 Console.WriteLine("PASS unjournaled nonempty database refuses implicit adoption");
 SqlFailure(Run(Grant("THROW 51000,'SYNTHETIC_GRANT_FAILURE',1;")),"SYNTHETIC_GRANT_FAILURE");
 Require(Tables()==0,"INITIAL_JOURNAL_OR_SCHEMA_NOT_ROLLED_BACK");
 Console.WriteLine("PASS initial script and journal creation roll back together");
 var first=Run(baseline);Require(first.Successful && first.Scripts.Count()==4 && Tables()==9 && History()==4,"FIRST_MIGRATION_FAILED");
 Require(Scalar("SELECT COUNT(*) FROM sys.database_permissions WHERE grantee_principal_id=USER_ID('fixture_reader') AND major_id=OBJECT_ID('registry.Destinations') AND permission_name='SELECT' AND state='G'")==1,"GRANT_NOT_COMMITTED");
 Sql("router","INSERT registry.Policies(Owner,Id,Source) VALUES('synthetic','keep','package synthetic');");
 var noop=Run(baseline);Require(noop.Successful && !noop.Scripts.Any() && History()==4 && Tables()==9,"INCREMENTAL_NOOP_RERUN_REQUIRED");
 Require(Scalar("SELECT COUNT(*) FROM registry.Policies WHERE Owner='synthetic' AND Id='keep'")==1,"BASELINE_DATA_CHANGED");
 Console.WriteLine("PASS first apply journals four versions; rerun executes zero scripts and preserves data");
 var added=baseline.Append(new SqlScript("050-add-probe.sql","CREATE TABLE registry.IncrementalProbe(Id int PRIMARY KEY); INSERT registry.IncrementalProbe VALUES(1);")).ToArray();
 var next=Run(added);Require(next.Successful && next.Scripts.Single().Name=="050-add-probe.sql" && History()==5 && Tables()==10,"NEW_VERSION_NOT_APPLIED_ONCE");
 Require(Run(added).Successful && Scalar("SELECT COUNT(*) FROM registry.IncrementalProbe")==1,"NEW_VERSION_REPLAYED");
 Console.WriteLine("PASS appended migration commits once with durable history");
 var changed=added.Select(s=>s.Name=="010-baseline.sql"?new SqlScript(s.Name,s.Contents+"\n-- changed"):s).ToArray();
 HistoryFailure(Run(changed));HistoryFailure(Run(baseline));
 Require(History()==5 && Tables()==10,"HISTORY_REJECTION_CHANGED_STATE");
 Require(Migration.Fingerprint("a\r\nb")==Migration.Fingerprint("a\nb"),"CROSS_PLATFORM_HASH_MISMATCH");
 Console.WriteLine("PASS applied-script edits and missing versions rejected; newline hashes portable");
 var failing=added.Append(new SqlScript("060-fail.sql","CREATE TABLE delivery.RollbackProbe(Id int); THROW 51000,'SYNTHETIC_LATER_FAILURE',1;")).ToArray();
 SqlFailure(Run(failing),"SYNTHETIC_LATER_FAILURE");Require(History()==5 && Tables()==10,"INCREMENTAL_ROLLBACK_FAILED");
 var batch=added.Append(new SqlScript("060-first.sql","CREATE TABLE delivery.RollbackProbe(Id int);")).Append(new SqlScript("070-fail.sql","THROW 51000,'SYNTHETIC_BATCH_FAILURE',1;")).ToArray();
 SqlFailure(Run(batch),"SYNTHETIC_BATCH_FAILURE");Require(History()==5 && Tables()==10,"BATCH_JOURNAL_ROLLBACK_FAILED");
 Console.WriteLine("PASS later failure rolls back all pending DDL and journal rows");
 // Real two-migrator overlap. A separate synthetic gate pauses the winner's
 // version while its migration lock is held; the loser must fail before history read.
 using var gate=new SqlConnection(cs+"router");gate.Open();
 using(var cmd=new SqlCommand("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource='synthetic-migration-gate',@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @r;",gate))Require((int)cmd.ExecuteScalar()>=0,"GATE_FAILED");
 var concurrent=added.Append(new SqlScript("060-concurrent.sql","DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource='synthetic-migration-gate',@LockMode='Shared',@LockOwner='Transaction',@LockTimeout=15000; IF @r<0 THROW 51000,'GATE_TIMEOUT',1; CREATE TABLE registry.ConcurrentProbe(Id int);")).ToArray();
 var winner=Task.Run(()=>Run(concurrent));
 try {
  var clock=Stopwatch.StartNew();bool held=false;
  while(clock.Elapsed<TimeSpan.FromSeconds(10)){
   using var check=new SqlCommand("SELECT APPLOCK_TEST('public','webhook-router-fresh-migration','Exclusive','Session');",gate);
   if((int)check.ExecuteScalar()==0){held=true;break;}await Task.Delay(50);
  }
  Require(held,"WINNER_LOCK_NOT_OBSERVED");
  SqlFailure(Run(concurrent),"MIGRATION_LOCK_UNAVAILABLE");
 } finally {using var release=new SqlCommand("EXEC sys.sp_releaseapplock @Resource='synthetic-migration-gate',@LockOwner='Session';",gate);release.ExecuteNonQuery();}
 var winning=await winner.WaitAsync(TimeSpan.FromSeconds(20));Require(winning.Successful && winning.Scripts.Count()==1 && History()==6,"CONCURRENT_WINNER_FAILED");
 var after=Run(concurrent);Require(after.Successful && !after.Scripts.Any() && History()==6,"CONCURRENT_VERSION_REPLAYED");
 Console.WriteLine("PASS concurrent loser fails closed; winner commits once; later rerun is no-op");
 Console.WriteLine("LIMIT: LocalDB integrated auth and synthetic grant, not Azure OIDC/runtime Entra users");
}finally{if(created){try{LocalDb("stop");}finally{LocalDb("delete");}}}
