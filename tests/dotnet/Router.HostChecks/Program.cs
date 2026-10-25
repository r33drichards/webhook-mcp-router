using System.Diagnostics;
using Azure.Storage.Queues;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Data.SqlClient;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using Router.Storage;
if(args.Length!=4)throw new ArgumentException("func, fixture root, opa, capabilities required");
var dbName="router_host_"+Guid.NewGuid().ToString("N");var master=@"Server=(localdb)\MSSQLLocalDB;Integrated Security=true;Encrypt=false;Initial Catalog=master";var connection=master.Replace("Initial Catalog=master","Initial Catalog="+dbName);
async Task Sql(string cs,string sql){await using var c=new SqlConnection(cs);await c.OpenAsync();await using var cmd=new SqlCommand(sql,c);await cmd.ExecuteNonQueryAsync();}
using var rsa=RSA.Create(2048);var signing=new RsaSecurityKey(rsa){KeyId="ephemeral-host-fixture"};var pub=rsa.ExportParameters(false);
string jwks=JsonSerializer.Serialize(new{keys=new[]{new{kty="RSA",use="sig",alg="RS256",kid=signing.KeyId,n=Base64UrlEncoder.Encode(pub.Modulus!),e=Base64UrlEncoder.Encode(pub.Exponent!)}}});
byte[] ingressKey=RandomNumberGenerator.GetBytes(32);
string Token(string client="a",string aud="router")=>new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor{Issuer="https://synthetic-issuer.example.invalid",Audience=aud,Expires=DateTime.UtcNow.AddMinutes(15),Claims=new Dictionary<string,object>{{"azp",client},{"sub","svc-"+client},{"scope","router:read requests:read subscriptions:write"}},SigningCredentials=new(signing,SecurityAlgorithms.RsaSha256)});
using var http=new HttpClient(new SocketsHttpHandler{UseProxy=false,AllowAutoRedirect=false}){BaseAddress=new Uri("http://127.0.0.1:7072"),Timeout=TimeSpan.FromSeconds(20)};
Process? host=null;Task? stdout=null,stderr=null;var log=new StringBuilder();
async Task Drain(StreamReader reader){while(await reader.ReadLineAsync() is string line){lock(log){if(log.Length<20000)log.AppendLine(line);}}}
async Task Start() {
 var p=new ProcessStartInfo(Path.GetFullPath(args[0])){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
 foreach(var value in new[]{"start","--no-build","--script-root",Path.GetFullPath(args[1]),"--port","7072","--address","127.0.0.1"})p.ArgumentList.Add(value);
 p.Environment["RouterQueue"]="UseDevelopmentStorage=true";p.Environment["AzureWebJobs.RouterReconcile.Disabled"]="true";
 p.Environment["FUNCTIONS_WORKER_RUNTIME"]="dotnet-isolated";p.Environment["AzureWebJobsStorage"]="UseDevelopmentStorage=true";p.Environment["AzureWebJobsSecretStorageType"]="files";p.Environment["FUNCTIONS_CORE_TOOLS_TELEMETRY_OPTOUT"]="1";
 p.Environment["ROUTER_HOST_FIXTURE"]=JsonSerializer.Serialize(new{Connection=connection,PublicJwks=jwks,IngressKey=Convert.ToBase64String(ingressKey),Opa=Path.GetFullPath(args[2]),Capabilities=Path.GetFullPath(args[3])});
 host=Process.Start(p)??throw new Exception("HOST_START_FAILED");stdout=Drain(host.StandardOutput);stderr=Drain(host.StandardError);
 for(int i=0;i<90;i++){if(host.HasExited)throw new Exception("HOST_EXITED");try{using var r=await http.PostAsync("/api/mcp",new StringContent("{}",Encoding.UTF8,"application/json"));if(r.StatusCode==HttpStatusCode.Unauthorized)return;}catch(HttpRequestException){}await Task.Delay(1000);}
 throw new Exception("HOST_START_TIMEOUT");
}
async Task Stop(){if(host is not null){if(!host.HasExited)host.Kill(true);await host.WaitForExitAsync();if(stdout is not null)await stdout;if(stderr is not null)await stderr;host.Dispose();host=null;}}
void Check(bool ok,string label){if(!ok)throw new Exception(label);Console.WriteLine("PASS HOST "+label);}
async Task<(int,JsonNode?)> Rpc(string method,object parameters,string? token) {
 using var request=new HttpRequestMessage(HttpMethod.Post,"/api/mcp"){Content=new StringContent(JsonSerializer.Serialize(new{jsonrpc="2.0",id=1,method,@params=parameters}),Encoding.UTF8,"application/json")};
 request.Headers.Accept.ParseAdd("application/json");request.Headers.Accept.ParseAdd("text/event-stream");if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
 using var response=await http.SendAsync(request);string text=await response.Content.ReadAsStringAsync();var line=text.Split('\n').LastOrDefault(l=>l.StartsWith("data: "));return((int)response.StatusCode,line is null?null:JsonNode.Parse(line[6..]));
}
async Task<JsonNode> Tool(string name,object arguments,string token){var(status,rpc)=await Rpc("tools/call",new{name,arguments},token);Check(status==200,"tool HTTP200 "+name);return rpc!["result"]!;}
JsonNode Data(JsonNode result)=>JsonNode.Parse(result["content"]![0]!["text"]!.GetValue<string>())!["result"]!;
async Task<int> Ingress(string id,byte[] body,bool valid){using var request=new HttpRequestMessage(HttpMethod.Post,"/api/webhooks/source-a"){Content=new ByteArrayContent(body)};request.Headers.Add("X-GitHub-Delivery",id);request.Headers.Add("X-GitHub-Event","issues");request.Headers.Add("X-Hub-Signature-256","sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(valid?ingressKey:new byte[32],body)));using var response=await http.SendAsync(request);return(int)response.StatusCode;}
var dispatchQueue=new QueueClient("UseDevelopmentStorage=true","router-dispatch",new QueueClientOptions{MessageEncoding=QueueMessageEncoding.Base64});
bool success=false;
try {
 await Sql(master,"CREATE DATABASE ["+dbName+"]");await SqlMigration.ApplyAsync(connection);
 await Sql(connection,"CREATE TABLE dbo.FixtureWakeup(Received int NOT NULL)");
 await dispatchQueue.CreateIfNotExistsAsync();await dispatchQueue.ClearMessagesAsync();
 await Start();
 await dispatchQueue.SendMessageAsync("{\"TenantId\":\"tenant-a\",\"SourceId\":\"source-a\"}");
 bool triggered=false;
 for(int attempt=0;attempt<45;attempt++) {
  await using var db=new SqlConnection(connection);await db.OpenAsync();await using var cmd=new SqlCommand("SELECT COUNT(*) FROM dbo.FixtureWakeup",db);
  if(Convert.ToInt32(await cmd.ExecuteScalarAsync())>0){triggered=true;break;}await Task.Delay(1000);
 }
 Check(triggered,"actual queue trigger deserializes wakeup and invokes runtime using local Azurite");var a=Token();var b=Token("b");
 Check((await Rpc("initialize",new{},null)).Item1==401,"missing bearer denied");Check((await Rpc("initialize",new{},Token(aud:"wrong"))).Item1==401,"wrong audience denied");
 var init=await Rpc("initialize",new{protocolVersion="2025-06-18",capabilities=new{},clientInfo=new{name="actual-host-fixture",version="1"}},a);Check(init.Item1==200&&init.Item2?["result"]?["capabilities"]?["events"] is not null,"authenticated SDK initialize");
 Check((await Rpc("tools/list",new{},a)).Item2?["result"]?["tools"]?.AsArray().Count==3,"exploration catalog");
 Check((await Rpc("events/list",new{},a)).Item2?["result"]?["events"]?.AsArray().Count==1,"custom event discovery");
 var body=Encoding.UTF8.GetBytes("{\"action\":\"opened\",\"number\":7,\"token\":\"synthetic-sensitive-marker\"}");
 Check(await Ingress("delivery-one",body,true)==200,"signed ingress accepted into SQL");
 var list=Data(await Tool("requests_list",new{},a));var items=list["Items"]!.AsArray();Check(items.Count==1,"durable request capture");var id=items[0]!["Request"]!["Id"]!.GetValue<string>();
 var detail=Data(await Tool("requests_detail",new{id},a));Check(!detail.ToJsonString().Contains("synthetic-sensitive-marker")&&detail["Redacted"]!.GetValue<bool>(),"stored payload redacted");
 Check(Data(await Tool("requests_list",new{},b))["Items"]!.AsArray().Count==0,"tenant B list isolation");Check((await Tool("requests_detail",new{id},b))["isError"]!.GetValue<bool>(),"tenant B detail denial");
 Check(Data(await Tool("requests_example",new{id},a))["untrustedData"]!.GetValue<bool>(),"policy example marked untrusted");
 await Stop();await Start();Check(Data(await Tool("requests_detail",new{id},a))["Id"]!.GetValue<string>()==id,"readback after fresh Functions host");
 Check(await Ingress("delivery-bad",body,false)==401,"bad signature rejected");
 Check(await Ingress("delivery-malformed",Encoding.UTF8.GetBytes("{not-json"),true)==400,"malformed signed input rejected");
 Check(await Ingress("delivery-oversized",new byte[65537],true)==413,"oversized input rejected");
 var final=Data(await Tool("requests_list",new{},a))["Items"]!.AsArray();Check(final.Count==4,"failed requests logged and exploration not captured");
 Check(final.Any(x=>x!["Request"]!["Authenticated"]!.GetValue<bool>()==false&&x["Request"]!["Payload"] is null),"unverified log metadata only");
 success=true;Console.WriteLine("LIMIT: actual Functions host with synthetic static signing-key DI and real LocalDB; production HTTPS JWKS retrieval and live Keycloak remain untested. No callback delivery attempted.");
} finally {
 await Stop();await dispatchQueue.DeleteIfExistsAsync();SqlConnection.ClearAllPools();await Sql(master,"IF DB_ID('"+dbName+"') IS NOT NULL BEGIN ALTER DATABASE ["+dbName+"] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE ["+dbName+"]; END");
 if(!success){/* Never print raw host logs: synthetic auth/signing fixture values may appear in diagnostics. */ Console.WriteLine("Host diagnostic withheld; failure assertion and host exit status identify stage.");}
}
