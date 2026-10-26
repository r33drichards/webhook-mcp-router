using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using Router.Auth;
using Router.Core;
using Router.Functions;
using Router.Mcp;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Net;
using var rsa=RSA.Create(2048);var key=new RsaSecurityKey(rsa){KeyId="fixture"};
var auth=new TokenValidator("https://issuer.example.invalid","router",[new("a","svc-a","tenant-a",["router:read","requests:read","subscriptions:write"]),new("b","svc-b","tenant-b",["router:read","requests:read","subscriptions:write"])],new Keys(key));
using var runtime=new FixtureRuntime(auth);var endpoints=new HttpEndpoints(runtime);
string Token(string client="a",string audience="router",string scope="router:read requests:read subscriptions:write")=>new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor{Issuer="https://issuer.example.invalid",Audience=audience,Expires=DateTime.UtcNow.AddMinutes(5),Claims=new Dictionary<string,object>{{"azp",client},{"sub","svc-"+client},{"scope",scope}},SigningCredentials=new(key,SecurityAlgorithms.RsaSha256)});
DefaultHttpContext? lastContext=null;
async Task<IActionResult> Send(string body,string? token=null,string method="POST",bool origin=false) {
 var context=new DefaultHttpContext();lastContext=context;var r=context.Request;r.Method=method;r.ContentType="application/json";r.Headers.Accept="application/json, text/event-stream";r.Body=new MemoryStream(Encoding.UTF8.GetBytes(body));
 if(token is not null)r.Headers.Authorization="Bearer "+token;if(origin)r.Headers.Origin="https://evil.example.invalid";
 return await endpoints.Mcp(r,CancellationToken.None);
}
void Check(bool ok,string name){if(!ok)throw new Exception(name);Console.WriteLine("PASS "+name);}
JsonElement Result(IActionResult result){var text=Encoding.UTF8.GetString(((FileContentResult)result).FileContents);var line=text.Split('\n').Last(l=>l.StartsWith("data: "));using var j=JsonDocument.Parse(line[6..]);return j.RootElement.Clone();}
string Rpc(string method,object p)=>JsonSerializer.Serialize(new{jsonrpc="2.0",id=1,method,@params=p});
Check(await Send("{}") is UnauthorizedResult,"HTTP missing bearer denied");
Check(lastContext!.Response.Headers.WWWAuthenticate==McpDiscovery.Challenge,"HTTP missing bearer advertises fixed metadata");
foreach(var verb in new[]{"GET","DELETE"}) {
 Check(await Send("{}",method:verb) is UnauthorizedResult,"HTTP unauthenticated verb denied "+verb);
 Check(lastContext!.Response.Headers.WWWAuthenticate==McpDiscovery.Challenge,"HTTP challenge for "+verb);
}
var metadataContext=new DefaultHttpContext();metadataContext.Request.Host=new HostString("attacker.invalid");metadataContext.Request.Headers["X-Forwarded-Host"]="attacker.invalid";metadataContext.Request.Headers.Authorization="Bearer synthetic-private-marker";
var metadata=(JsonResult)endpoints.Metadata(metadataContext.Request);var doc=JsonSerializer.SerializeToElement(metadata.Value);
Check(metadata.StatusCode==200&&metadata.ContentType=="application/json","HTTP public metadata JSON");
Check(doc.GetProperty("resource").GetString()==McpDiscovery.Resource&&doc.GetProperty("authorization_servers")[0].GetString()==McpDiscovery.Issuer,"HTTP canonical resource and issuer");
Check(doc.GetProperty("bearer_methods_supported")[0].GetString()=="header"&&doc.GetProperty("scopes_supported").GetArrayLength()==3,"HTTP only read scopes advertised");
Check(!doc.GetRawText().Contains("attacker")&&!doc.GetRawText().Contains("synthetic-private-marker")&&!doc.TryGetProperty("registration_endpoint",out _),"HTTP metadata cannot reflect host/token or offer registration");
Check(runtime.LastTenant is null&&runtime.LogAppends==0,"HTTP discovery has no tenant dispatch or log side effect");
Check(await Send("{}",Token(audience:"other")) is StatusCodeResult{StatusCode:401},"HTTP wrong audience denied");
Check(lastContext!.Response.Headers.WWWAuthenticate==McpDiscovery.Challenge,"HTTP rejected token advertises discovery without token details");
Check(await Send("{}","not-a-jwt") is StatusCodeResult{StatusCode:401},"HTTP malformed token remains denied");
Check(await Send("{}",Token(scope:"requests:read")) is StatusCodeResult{StatusCode:403},"HTTP missing route scope denied");
Check(await Send("{}",Token(),origin:true) is StatusCodeResult{StatusCode:403},"HTTP origin denied");
Check(await Send("{}",Token(),method:"GET") is StatusCodeResult{StatusCode:405},"HTTP stateless GET unsupported");
var init=Result(await Send(Rpc("initialize",new{protocolVersion="2025-06-18",capabilities=new{},clientInfo=new{name="synthetic",version="1"}}),Token()));
Check(init.GetProperty("result").GetProperty("capabilities").TryGetProperty("events",out _),"HTTP handler authenticated SDK initialize");
var call=Result(await Send(Rpc("tools/call",new{name="requests_list",arguments=new{}}),Token()));
Check(!call.GetProperty("result").GetProperty("isError").GetBoolean()&&runtime.LastTenant=="tenant-a","HTTP trusted tenant A tool dispatch");
await Send(Rpc("tools/call",new{name="requests_list",arguments=new{}}),Token("b"));Check(runtime.LastTenant=="tenant-b","HTTP trusted tenant B dispatch");
var denied=Result(await Send(Rpc("tools/call",new{name="requests_list",arguments=new{tenant="tenant-b"}}),Token()));Check(denied.GetProperty("result").GetProperty("isError").GetBoolean(),"HTTP arbitrary tenant argument rejected");
Check(await Send(new string('x',65537),Token()) is StatusCodeResult{StatusCode:413},"HTTP bounded MCP body");
Check(await Send("not-json",Token()) is BadRequestResult,"HTTP malformed MCP rejected");
var delivery=new{mode="webhook",url="https://callback.example.invalid",secret="whsec_"+Convert.ToBase64String(runtime.CallbackKey)};
var subscribed=Result(await Send(Rpc("events/subscribe",new{name=EventService.EventName,arguments=new{},delivery}),Token()));
string subscription=subscribed.GetProperty("result").GetProperty("id").GetString()!;
Check(runtime.Writes.Any(s=>s.Id==subscription&&s.Owner=="tenant-a"),"HTTP custom subscribe with signed synthetic verification");
await Send(Rpc("events/unsubscribe",new{name=EventService.EventName,arguments=new{},delivery=new{mode="webhook",url="https://callback.example.invalid"}}),Token("b"));
Check(runtime.Writes.Any(s=>s.Id==subscription),"HTTP tenant B cannot unsubscribe tenant A");
await Send(Rpc("events/unsubscribe",new{name=EventService.EventName,arguments=new{},delivery=new{mode="webhook",url="https://callback.example.invalid"}}),Token());
Check(!runtime.Writes.Any(s=>s.Id==subscription),"HTTP owning tenant unsubscribe");
Check(runtime.LogAppends==0,"HTTP MCP does not create webhook logs");
using(var missing=new RouterRuntime()) {
 var noConfig=new HttpEndpoints(missing);
 Check(noConfig.Metadata(new DefaultHttpContext().Request) is JsonResult{StatusCode:200},"public discovery needs no private configuration");
 var context=new DefaultHttpContext();context.Request.Method="POST";context.Request.Body=new MemoryStream(Encoding.UTF8.GetBytes("{}"));
 Check(await noConfig.Webhook(context.Request,"unknown",CancellationToken.None) is StatusCodeResult{StatusCode:503},"missing server configuration is503, not client JSON400");
}
sealed class Keys(SecurityKey key):ISigningKeys{public Task<IReadOnlyList<SecurityKey>> GetAsync(bool refresh,CancellationToken ct)=>Task.FromResult<IReadOnlyList<SecurityKey>>([key]);}
sealed class FixtureRuntime(TokenValidator validator):IRouterRuntime,IDisposable {
 public TokenValidator Validator=>validator;public string? LastTenant;public int LogAppends;public byte[] CallbackKey {get;}=RandomNumberGenerator.GetBytes(32);public List<Subscription> Writes {get;}=[];
 private HttpClient? http;
 public RequestServer Mcp(TenantContext tenant){LastTenant=tenant.TenantId;http??=new HttpClient(new Callback(CallbackKey));return new(tenant,new RequestExplorer(tenant,new Log(this)),new EventService(new Writer(this,tenant),"https://callback.example.invalid",CallbackKey,http));}
 public LoggedIngress? Ingress(string source)=>null;
 public void Dispose()=>http?.Dispose();
 sealed class Log(FixtureRuntime owner):IRequestLog {
  public Task AppendAsync(CapturedRequest r,CancellationToken ct){owner.LogAppends++;return Task.CompletedTask;}
  public Task<RequestLogPage> ListAsync(int limit,long? before,CancellationToken ct)=>Task.FromResult(new RequestLogPage([],null));
  public Task<CapturedRequest?> FindAsync(string id,CancellationToken ct)=>Task.FromResult<CapturedRequest?>(null);
 }
 sealed class Writer(FixtureRuntime owner,TenantContext tenant):IRegistrationWriter {
  public Task SaveSubscriptionAsync(Subscription s,CancellationToken ct){tenant.Match(s.Owner);owner.Writes.RemoveAll(x=>x.Id==s.Id&&x.Owner==s.Owner);owner.Writes.Add(s);return Task.CompletedTask;}
  public Task DeleteSubscriptionAsync(string o,string id,CancellationToken ct){tenant.Match(o);owner.Writes.RemoveAll(x=>x.Id==id&&x.Owner==o);return Task.CompletedTask;}
  public Task SavePolicyAsync(string o,StoredPolicy p,CancellationToken ct)=>throw new Exception("unexpected policy write");
 }
 sealed class Callback(byte[] key):HttpMessageHandler {
  protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken ct){string body=await r.Content!.ReadAsStringAsync(ct);string id=r.Headers.GetValues("webhook-id").Single(),timestamp=r.Headers.GetValues("webhook-timestamp").Single();string signature="v1,"+Convert.ToBase64String(HMACSHA256.HashData(key,Encoding.UTF8.GetBytes(id+"."+timestamp+"."+body)));if(r.Headers.GetValues("webhook-signature").Single()!=signature)throw new Exception("bad signature");using var j=JsonDocument.Parse(body);return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(JsonSerializer.Serialize(new{challenge=j.RootElement.GetProperty("challenge").GetString()}))};}
 }
}

