using DbUp;
using DbUp.Engine;
using Microsoft.Data.SqlClient;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
namespace Router.Migrator;
public static class Migration {
 internal static readonly string[] Baseline=["010-baseline.sql","020-destinations.sql","030-runtime-grants.sql","040-verify.sql"];
 public static string ReadResource(string name) {
  using var stream=typeof(Migration).Assembly.GetManifestResourceStream(name)??throw new InvalidOperationException("SCRIPT_MISSING");
  using var reader=new StreamReader(stream);return reader.ReadToEnd();
 }
 public static SqlScript[] Scripts() {
  var names=typeof(Migration).Assembly.GetManifestResourceNames().Where(n=>n.EndsWith(".sql",StringComparison.OrdinalIgnoreCase)).ToArray();
  if(names.Any(n=>!Regex.IsMatch(n,@"^[0-9]{3}-[a-z0-9-]+\.sql$")))throw new InvalidOperationException("INVALID_MIGRATION_RESOURCE_NAME");
  return names.Where(n=>n!="000-preflight.sql").Order(StringComparer.Ordinal).Select(n=>new SqlScript(n,ReadResource(n))).ToArray();
 }
 public static string Fingerprint(string contents)=>Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(contents.Replace("\r\n","\n"))));
 internal static void Validate(SqlScript[] scripts) {
  if(scripts.Length<Baseline.Length || !scripts.Take(Baseline.Length).Select(s=>s.Name).SequenceEqual(Baseline)
   || scripts.Any(s=>!Regex.IsMatch(s.Name,@"^[0-9]{3}-[a-z0-9-]+\.sql$"))
   || scripts.Select(s=>s.Name).Distinct(StringComparer.Ordinal).Count()!=scripts.Length
   || !scripts.Select(s=>s.Name).SequenceEqual(scripts.Select(s=>s.Name).Order(StringComparer.Ordinal)))
   throw new InvalidOperationException("APPEND_ONLY_MANIFEST_REQUIRED");
 }
 public static DatabaseUpgradeResult Run(Func<SqlConnection> connection,SqlScript[] scripts) {
  Validate(scripts);
  var builder=DeployChanges.To.SqlDatabase(connection).WithScripts(scripts).LogToNowhere().WithTransaction().WithExecutionTimeout(TimeSpan.FromSeconds(120));
  builder.Configure(c=>c.Journal=new TransactionalJournal(c.ConnectionManager,scripts));
  return builder.Build().PerformUpgrade();
 }
}
