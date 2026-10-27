using Router.Core;
using Router.Mcp;
using System.Text;
using System.Text.Json;
var tenant=new TenantContext("tenant-a","client-a",["router:read","requests:read","subscriptions:write"]);
var log=new Log();using var http=new HttpClient(new NoNetwork());
DestinationManagement? management=null;PolicyManagement? policies=null;
var events=new EventService(new Writer(),"https://callback.example.invalid",new byte[32],http);
async Task<JsonElement> Call(string method,string parameters) {
 // New server for every request: no in-memory MCP session dependence.
 var server=new RequestServer(tenant,new RequestExplorer(tenant,log),events,management,policies);
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

var store=new DestinationMemory();
tenant=new TenantContext("tenant-a","writer",["router:read","requests:read","destinations:read","destinations:write"]);
management=new DestinationManagement(tenant,store,[new("approved","https://private.example.invalid/hidden","key-ref")]);
var catalog=await Call("tools/list","{}");Check(catalog.GetProperty("result").GetProperty("tools").GetArrayLength()==8,"destination tool catalog uses metadata-only surface");
var registered=await Call("tools/call","""{"name":"destinations_register","arguments":{"binding":"approved","name":"Review team","tags":["review"]}}""");
Check(!registered.GetProperty("result").GetProperty("isError").GetBoolean()&&store.Rows.Single().Value.Metadata.Enabled==false,"MCP destination registration starts disabled");
Check(!registered.GetRawText().Contains("private.example")&&!registered.GetRawText().Contains("key-ref"),"MCP never returns protected binding URL or key reference");
var id=store.Rows.Single().Key;
var enabled=await Call("tools/call",JsonSerializer.Serialize(new{name="destinations_set_enabled",arguments=new{id,enabled=true}}));
Check(!enabled.GetProperty("result").GetProperty("isError").GetBoolean()&&store.Rows[id].Metadata.Enabled,"MCP owning tenant explicitly enables destination");
var before=store.Writes;
var extra=await Call("tools/call","""{"name":"destinations_register","arguments":{"binding":"approved","name":"Bad","tags":[],"tenant":"other"}}""");
Check(extra.GetProperty("result").GetProperty("isError").GetBoolean()&&store.Writes==before,"unknown tenant argument rejected before destination write");
tenant=new TenantContext("tenant-b","reader",["router:read","destinations:read"]);management=new DestinationManagement(tenant,store,[]);
var denied=await Call("tools/call",JsonSerializer.Serialize(new{name="destinations_set_enabled",arguments=new{id,enabled=false}}));
Check(denied.GetProperty("result").GetProperty("isError").GetBoolean()&&store.Rows[id].Metadata.Enabled,"MCP missing destination write scope denied");
var other=await Call("tools/call","""{"name":"destinations_list","arguments":{}}""");
Check(!other.GetRawText().Contains(id),"MCP other tenant destination list does not leak ID");
Check(log.Appends==0,"destination management never creates webhook examples");

var policyStore=new PolicyMemory();
tenant=new TenantContext("tenant-a","policy-reader",["router:read","policies:read"]);
policies=new PolicyManagement(tenant,policyStore,new PolicyDestinations(),new OpaEvaluator("invalid","invalid"),"source-a");
var policyCatalog=await Call("tools/list","{}");
Check(policyCatalog.GetProperty("result").GetProperty("tools").EnumerateArray().Count(t=>t.GetProperty("name").GetString()!.StartsWith("policies_"))==4,"four explicit policy tools advertised");
Check(!(await Call("tools/call", """{"name":"policies_get","arguments":{}}""")).GetProperty("result").GetProperty("isError").GetBoolean(),"authorized policy get succeeds without evaluator or mutation");
foreach(var payload in new[]{
 """{"name":"policies_apply","arguments":{"id":"route","source":"package router","expected_revision":null}}""",
 """{"name":"policies_get","arguments":{"tenant":"tenant-b"}}""",
 """{"name":"policies_validate","arguments":{"source":"package router"}}"""})
 Check((await Call("tools/call",payload)).GetProperty("result").GetProperty("isError").GetBoolean(),"policy scope/unknown tenant denied");
Check(policyStore.Writes==0&&log.Appends==0,"policy permission failures neither write nor capture webhook examples");

sealed class PolicyMemory:IPolicyStore {
 public int Writes;
 public Task<ManagedPolicy?> GetAsync(CancellationToken ct)=>Task.FromResult<ManagedPolicy?>(null);
 public Task<ManagedPolicy> ApplyAsync(string id,string source,string? expected,CancellationToken ct){Writes++;throw new Exception("unexpected write");}
}
sealed class PolicyDestinations:IDestinationReader {public Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string tenant,CancellationToken ct)=>Task.FromResult<IReadOnlyList<RegisteredDestination>>([]);}

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

sealed class DestinationMemory:IDestinationStore {
 public Dictionary<string,(string Owner,DestinationMetadata Metadata)> Rows=[];public int Writes;
 public Task<DestinationPage> ListAsync(string tenantId,int limit,string? after,CancellationToken ct)=>Task.FromResult(new DestinationPage(Rows.Values.Where(x=>x.Owner==tenantId).Select(x=>x.Metadata).ToArray(),null));
 public Task AddAsync(string tenantId,DestinationMetadata metadata,ProtectedDestination binding,CancellationToken ct){Rows.Add(metadata.Id,(tenantId,metadata));Writes++;return Task.CompletedTask;}
 public Task UpdateAsync(string tenantId,string id,string name,string[] tags,CancellationToken ct){if(!Rows.TryGetValue(id,out var row)||row.Owner!=tenantId)throw new UnauthorizedAccessException();Rows[id]=(tenantId,row.Metadata with{Name=name,Tags=tags});Writes++;return Task.CompletedTask;}
 public Task SetEnabledAsync(string tenantId,string id,bool enabled,CancellationToken ct){if(!Rows.TryGetValue(id,out var row)||row.Owner!=tenantId)throw new UnauthorizedAccessException();Rows[id]=(tenantId,row.Metadata with{Enabled=enabled});Writes++;return Task.CompletedTask;}
}
