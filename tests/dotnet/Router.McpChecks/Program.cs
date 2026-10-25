using Router.Core;
using Router.Mcp;
using System.Text;
using System.Text.Json;
var tenant=new TenantContext("tenant-a","client-a",["router:read","requests:read","subscriptions:write"]);
var log=new Log();using var http=new HttpClient(new NoNetwork());
var events=new EventService(new Writer(),"https://callback.example.invalid",new byte[32],http);
async Task<JsonElement> Call(string method,string parameters) {
 // New server for every request: no in-memory MCP session dependence.
 var server=new RequestServer(tenant,new RequestExplorer(tenant,log),events);
 using var output=new MemoryStream();
 bool wrote=await server.ProcessAsync(Encoding.UTF8.GetBytes("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\""+method+"\",\"params\":"+parameters+"}"),output,CancellationToken.None);
 string body=Encoding.UTF8.GetString(output.ToArray());
 var data=body.Split('\n').LastOrDefault(l=>l.StartsWith("data: ",StringComparison.Ordinal))?[6..]??body;
 using var json=JsonDocument.Parse(data);if(!wrote)throw new Exception("missing response");return json.RootElement.Clone();
}
void Check(bool ok,string name){if(!ok)throw new Exception(name);Console.WriteLine("PASS "+name);}
var initialized=await Call("initialize","{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"synthetic\",\"version\":\"1\"}}");
Check(initialized.GetProperty("result").GetProperty("capabilities").TryGetProperty("events",out _),"official SDK advertises custom events capability");
var tools=await Call("tools/list","{}");Check(tools.GetProperty("result").GetProperty("tools").GetArrayLength()==3,"fresh-instance tools list");
var list=await Call("tools/call","{\"name\":\"requests_list\",\"arguments\":{}}");Check(!list.GetProperty("result").GetProperty("isError").GetBoolean(),"fresh-instance exploration tool call");
Check((await Call("events/list","{}")).GetProperty("result").GetProperty("events").GetArrayLength()==1,"custom events discovery");
Check(log.Appends==0,"MCP exploration does not capture webhook requests");
sealed class NoNetwork:HttpMessageHandler {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken c)=>throw new Exception("No network permitted");}
sealed class Log:IRequestLog {
 public int Appends;
 public Task AppendAsync(CapturedRequest r,CancellationToken ct){Appends++;return Task.CompletedTask;}
 public Task<RequestLogPage> ListAsync(int limit,long? before,CancellationToken ct)=>Task.FromResult(new RequestLogPage([],null));
 public Task<CapturedRequest?> FindAsync(string id,CancellationToken ct)=>Task.FromResult<CapturedRequest?>(null);
}
sealed class Writer:IRegistrationWriter {
 public Task SaveSubscriptionAsync(Subscription s,CancellationToken ct)=>throw new Exception("unexpected write");
 public Task DeleteSubscriptionAsync(string o,string id,CancellationToken ct)=>throw new Exception("unexpected write");
 public Task SavePolicyAsync(string o,StoredPolicy p,CancellationToken ct)=>throw new Exception("unexpected write");
}
