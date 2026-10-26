using Azure.Core;
using Azure.Identity;
using Microsoft.Data.SqlClient;
using Router.SqlBootstrap;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;

// Operator-only draft. No ARM client, persistence cache, token output or CI login.
static void Require(bool ok){if(!ok)throw new InvalidOperationException("BOOTSTRAP_CONTRACT_DENIED");}
static JsonDocument Claims(string token){var p=token.Split('.')[1].Replace('-','+').Replace('_','/');return JsonDocument.Parse(Convert.FromBase64String(p.PadRight((p.Length+3)/4*4,'=')));}
try {
 Require(args.Length>=2 && args[0] is "plan" or "probe" or "apply");
 var migrator=Guid.Parse(args[1]);var sql=Bootstrap.Build(migrator);var hash=Bootstrap.Hash(sql);
 if(args[0]=="plan"){Require(args.Length==2);Console.WriteLine(sql);Console.WriteLine("BOOTSTRAP_SQL_SHA256="+hash);return 0;}
 Require(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true");
 Require(Environment.GetEnvironmentVariable("ROUTER_BOOTSTRAP_APPROVED")=="true");
 Require(args.Length==(args[0]=="apply"?3:2));
 if(args[0]=="apply")Require(args[2]==hash);
 // Use only the operator's approved local Azure CLI session. No login,
 // interactive fallback or token-cache copying is performed by this helper.
 using var timeout=new CancellationTokenSource(TimeSpan.FromMinutes(5));
 var credential=new AzureCliCredential(new AzureCliCredentialOptions {
  TenantId=Bootstrap.Tenant,ProcessTimeout=TimeSpan.FromSeconds(30)
 });
 var token=await credential.GetTokenAsync(new TokenRequestContext(["https://database.windows.net/.default"]),timeout.Token);
 using(var claims=Claims(token.Token)){var c=claims.RootElement;
  Require(c.GetProperty("tid").GetString()==Bootstrap.Tenant && c.GetProperty("oid").GetString()==Bootstrap.Administrator && c.GetProperty("aud").GetString()=="https://database.windows.net/" && c.GetProperty("exp").GetInt64()>DateTimeOffset.UtcNow.ToUnixTimeSeconds()+120);
 }
 using var connection=new SqlConnection($"Server=tcp:{Bootstrap.Server},1433;Initial Catalog=router;Encrypt=True;TrustServerCertificate=False;Connect Timeout=20;Pooling=False;Application Name=Router.SqlBootstrap"){AccessToken=token.Token};
 if(args[0]=="probe") {
  try {await connection.OpenAsync(timeout.Token);Console.WriteLine("BOOTSTRAP_ALREADY_REACHABLE_UNEXPECTED");return 3;}
  catch(SqlException e)when(e.Number==40615){
   var match=Regex.Match(e.Message,@"Client with IP address '([0-9.]+)'",RegexOptions.CultureInvariant);
   Require(match.Success && IPAddress.TryParse(match.Groups[1].Value,out var parsed) && parsed.AddressFamily==System.Net.Sockets.AddressFamily.InterNetwork);
   Console.WriteLine(JsonSerializer.Serialize(new{serverObservedTdsIpv4=match.Groups[1].Value,sqlError=40615}));return 0;
  }
 }
 await Bootstrap.Execute(connection,sql,timeout.Token);
 Console.WriteLine("PASS_BOOTSTRAP_FOUR_USERS_TWO_SCHEMAS_EIGHT_EXPLICIT_GRANTS");return 0;
} catch {Console.Error.WriteLine("BOOTSTRAP_FAILED_OR_COMMIT_UNCERTAIN; no automatic retry; operator must verify SQL and network closure");return 1;}
