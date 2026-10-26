using DbUp.Engine;
using DbUp.Engine.Transactions;
using System.Data;
namespace Router.Migrator;
// All operations use DbUp's managed connection and single transaction. The lock
// is acquired before history selection, including no-op runs, never in a later script.
internal sealed class TransactionalJournal(IConnectionManager manager,SqlScript[] scripts):IJournal {
 bool prepared;
 public string[] GetExecutedScripts()=>manager.ExecuteCommandsWithManagedConnection(factory=> {
  using(var command=factory()){command.CommandText=Migration.ReadResource("000-preflight.sql");command.ExecuteNonQuery();}
  var rows=new List<(string Name,string Hash)>();
  using(var command=factory()) {
   command.CommandText="SELECT ScriptName,ContentHash FROM registry.SchemaVersions ORDER BY ScriptName COLLATE Latin1_General_100_BIN2";
   using var reader=command.ExecuteReader();while(reader.Read())rows.Add((reader.GetString(0),reader.GetString(1)));
  }
  if(rows.Count>scripts.Length || (rows.Count>0 && rows.Count<Migration.Baseline.Length))throw new InvalidOperationException("JOURNAL_HISTORY_MISMATCH");
  for(int i=0;i<rows.Count;i++)
   if(rows[i].Name!=scripts[i].Name || rows[i].Hash!=Migration.Fingerprint(scripts[i].Contents))throw new InvalidOperationException("APPLIED_MIGRATION_CHANGED_OR_MISSING");
  prepared=true;return rows.Select(r=>r.Name).ToArray();
 });
 public void EnsureTableExistsAndIsLatestVersion(Func<IDbCommand> factory) {
  if(!prepared)throw new InvalidOperationException("JOURNAL_PREFLIGHT_REQUIRED");
 }
 public void StoreExecutedScript(SqlScript script,Func<IDbCommand> factory) {
  EnsureTableExistsAndIsLatestVersion(factory);
  using var command=factory();
  command.CommandText="INSERT registry.SchemaVersions(ScriptName,ContentHash) VALUES(@name,@hash)";
  var name=command.CreateParameter();name.ParameterName="@name";name.Value=script.Name;command.Parameters.Add(name);
  var hash=command.CreateParameter();hash.ParameterName="@hash";hash.Value=Migration.Fingerprint(script.Contents);command.Parameters.Add(hash);
  command.ExecuteNonQuery();
 }
}
