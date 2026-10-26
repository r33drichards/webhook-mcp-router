using Azure.Core;
using Azure.Identity;
using DbUp;
using DbUp.Engine;
using DbUp.Helpers;
using Microsoft.Data.SqlClient;
using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

// Standalone Actions tool: never referenced by the Function application.
const string tenant="0e4545fd-804f-4acb-ad41-f955e53645c1";
const string server="sql-webhook-mcp-router-v2-f7076f8e38.database.windows.net";
const string subject="repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router";
static string Required(string key)=>Environment.GetEnvironmentVariable(key)??throw new InvalidOperationException("CONFIG_REQUIRED");
static JsonDocument Claims(string jwt) {var part=jwt.Split('.')[1].Replace('-','+').Replace('_','/');return JsonDocument.Parse(Convert.FromBase64String(part.PadRight((part.Length+3)/4*4,'=')));}
static void Require(bool ok){if(!ok)throw new InvalidOperationException("CONTRACT_DENIED");}
string stage="arguments";
try {
 Require(args.Length==1 && args[0] is "manifest" or "probe" or "migrate");
 var scripts=Router.Migrator.Migration.Scripts();
 if(args[0]=="manifest") {Console.WriteLine(JsonSerializer.Serialize(new[]{new SqlScript("000-preflight.sql",Router.Migrator.Migration.ReadResource("000-preflight.sql"))}.Concat(scripts).Select(s=>new{name=s.Name,sha256=Router.Migrator.Migration.Fingerprint(s.Contents)})));return 0;}
 Require(Required("GITHUB_REPOSITORY")=="r33drichards/webhook-mcp-router" && Required("GITHUB_REF")=="refs/heads/main");
 string client=Guid.Parse(Required("MIGRATION_CLIENT_ID")).ToString(),principal=Guid.Parse(Required("MIGRATION_PRINCIPAL_ID")).ToString();
 using var http=new HttpClient(){Timeout=TimeSpan.FromSeconds(20)};
 stage="GITHUB_TOKEN_EXCHANGE";
 var credential=new ClientAssertionCredential(tenant,client,async cancellation=> {
  stage="GITHUB_TOKEN_REQUEST";
  var endpoint=Required("ACTIONS_ID_TOKEN_REQUEST_URL");Require(new Uri(endpoint).Scheme=="https");
  using var request=new HttpRequestMessage(HttpMethod.Get,endpoint+(endpoint.Contains('?')?'&':'?')+"audience=api%3A%2F%2FAzureADTokenExchange");
  request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",Required("ACTIONS_ID_TOKEN_REQUEST_TOKEN"));
  using var response=await http.SendAsync(request,cancellation);response.EnsureSuccessStatusCode();
  using var data=JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellation));var token=data.RootElement.GetProperty("value").GetString()!;
  stage="GITHUB_TOKEN_CLAIMS";
  using var claims=Claims(token);var c=claims.RootElement;
  Require(c.GetProperty("iss").GetString()=="https://token.actions.githubusercontent.com" && c.GetProperty("sub").GetString()==subject && c.GetProperty("aud").GetString()=="api://AzureADTokenExchange" && c.GetProperty("exp").GetInt64()>DateTimeOffset.UtcNow.ToUnixTimeSeconds()+60);
  stage="SQL_TOKEN_EXCHANGE";
  return token;
 });
 stage="SQL_TOKEN_ACQUISITION";
 var access=await credential.GetTokenAsync(new TokenRequestContext(["https://database.windows.net/.default"]));
 stage="SQL_TOKEN_CLAIMS";
 using(var claims=Claims(access.Token)){var c=claims.RootElement;Require(c.GetProperty("tid").GetString()==tenant && c.GetProperty("oid").GetString()==principal && c.GetProperty("appid").GetString()==client && (c.GetProperty("aud").GetString() is "https://database.windows.net" or "https://database.windows.net/"));}
 var connectionString=$"Server=tcp:{server},1433;Initial Catalog=router;Encrypt=True;TrustServerCertificate=False;Connect Timeout=20;Pooling=False;Application Name=Router.DbUp.Migrator";
 SqlConnection Connect()=>new(connectionString){AccessToken=access.Token};
 if(args[0]=="probe") {
  stage="TDS_PROBE_CONNECT";
  try {using var connection=Connect();await connection.OpenAsync();Console.WriteLine("TDS_ALREADY_REACHABLE_UNEXPECTED");return 3;}
  catch(SqlException e)when(e.Number==40615) {
   stage="FIREWALL_RESPONSE_PARSE";
   var match=Regex.Match(e.Message,@"Client with IP address '([0-9.]+)'",RegexOptions.CultureInvariant);
   Require(match.Success && IPAddress.TryParse(match.Groups[1].Value,out _));var ip=IPAddress.Parse(match.Groups[1].Value);var b=ip.GetAddressBytes();
   Require(b.Length==4 && b[0] is >0 and <224 && b[0]!=10 && b[0]!=127 && !(b[0]==169&&b[1]==254) && !(b[0]==172&&b[1]>=16&&b[1]<=31) && !(b[0]==192&&b[1]==168));
   Console.WriteLine(JsonSerializer.Serialize(new{serverObservedTdsIpv4=ip.ToString(),sqlError=40615}));return 0;
  }
 }
 // Journal and pending scripts commit together; unchanged manifests execute no scripts.
 stage="MIGRATION_TRANSACTION";
 var result=Router.Migrator.Migration.Run(Connect,scripts);
 if(!result.Successful){Console.WriteLine("MIGRATION_TRANSACTION_FAILED_DETAILS_WITHHELD");return 1;}
 Console.WriteLine("PASS_INCREMENTAL_MIGRATION_TRANSACTION applied="+result.Scripts.Count());return 0;
} catch(Exception error) {
 // Never emit exception text, token claims, command arguments or connection strings.
 var category=error switch {SqlException=>"SQL",AuthenticationFailedException=>"TOKEN_ACQUISITION",OperationCanceledException=>"CANCELLED",HttpRequestException=>"HTTP",InvalidOperationException=>"CONTRACT",KeyNotFoundException=>"MISSING_FIELD",JsonException=>"JSON",FormatException=>"FORMAT",_=>"OTHER"};
 var codes=error is SqlException sqlError ? sqlError.Errors.Cast<SqlError>().Take(4).Select(e=>new{number=e.Number,state=e.State,severity=e.Class}).ToArray() : [];
 Console.Error.WriteLine(JsonSerializer.Serialize(new{stage,category,sqlErrors=codes}));
 Console.WriteLine("MIGRATION_STAGE_FAILED_DETAILS_WITHHELD");return 1;
}
