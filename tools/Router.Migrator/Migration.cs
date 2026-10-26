using DbUp;
using DbUp.Engine;
using DbUp.Helpers;
using Microsoft.Data.SqlClient;
namespace Router.Migrator;
public static class Migration {
 public static SqlScript[] Scripts() {
  var assembly=typeof(Migration).Assembly;
  return new[]{"000-fresh.sql","010-baseline.sql","020-destinations.sql","030-runtime-grants.sql","040-verify.sql"}.Select(name=> {
   using var stream=assembly.GetManifestResourceStream(name)??throw new InvalidOperationException("SCRIPT_MISSING");
   using var reader=new StreamReader(stream);return new SqlScript(name,reader.ReadToEnd());
  }).ToArray();
 }
 public static DatabaseUpgradeResult Run(Func<SqlConnection> connection,SqlScript[] scripts)=>DeployChanges.To.SqlDatabase(connection).WithScripts(scripts).LogToNowhere().WithTransaction().JournalTo(new NullJournal()).WithExecutionTimeout(TimeSpan.FromSeconds(120)).Build().PerformUpgrade();
}
