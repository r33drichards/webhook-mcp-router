using System.Text.Json;
using Router.Core;
int count=0;
void Check(bool ok){if(!ok)throw new Exception("CHECK_FAILED");count++;}
async Task Denied(Func<Task> f){try{await f();}catch(Exception e)when(e is UnauthorizedAccessException or InvalidOperationException or ArgumentException){count++;return;}throw new Exception("EXPECTED_DENIAL");}
var opa=new OpaEvaluator(Path.GetFullPath(args[0]),Path.GetFullPath(args[1]));
var tenant=new TenantContext("tenant-a","actor",["policies:read","policies:test","policies:write"]);
var store=new MemoryStore();var dest=new Destinations();var service=new PolicyManagement(tenant,store,dest,opa,"source-a");
string deny="package router\ndefault routes := []";
string allow="package router\nroutes := [{\"destination_id\": d.id, \"payload\": input.original}] if { some d in input.destinations; d.name == \"review\"; input.original.action == \"labeled\" }\ndefault routes := []";
Check(await service.GetAsync(default)==null);
await service.ValidateAsync(deny,default);count++;
await Denied(()=>service.ValidateAsync("not rego",default));
await Denied(()=>service.ValidateAsync("package router\nroutes := http.send({\"method\":\"GET\",\"url\":\"https://example.com\"})",default));
Check(store.Writes==0);
var input=JsonSerializer.SerializeToElement(new{action="labeled"});
var preview=await service.PreviewAsync(allow,"pull_request",input,default);
Check(preview.Allowed&&preview.Routes.Count==1&&preview.Routes[0].DestinationId=="dest-a"&&store.Writes==0);
preview=await service.PreviewAsync(deny,"pull_request",input,default);Check(!preview.Allowed&&preview.Routes.Count==0);
preview=await service.PreviewAsync("package router\nroutes := [{\"destination_id\":\"dest-b\",\"payload\":input.original}]","pull_request",input,default);Check(!preview.Allowed&&preview.Routes.Count==0);
await Denied(()=>service.PreviewAsync(deny,"bad/event",input,default));
await Denied(()=>service.PreviewAsync(deny,"pull_request",JsonSerializer.SerializeToElement(new string('a',70000)),default));
var first=await service.ApplyAsync("route",deny,null,default);Check(first.Revision=="0000000000000001"&&store.Writes==1);
await Denied(()=>service.ApplyAsync("route",allow,null,default));
await Denied(()=>service.ApplyAsync("other",allow,first.Revision,default));
await Denied(()=>service.ApplyAsync("route",allow,"0000000000000000",default));
await Denied(()=>service.ApplyAsync("route","broken",first.Revision,default));Check(store.Writes==1);
var second=await service.ApplyAsync("route",allow,first.Revision,default);Check(second.Revision!=first.Revision&&store.Writes==2);
await Denied(()=>service.ApplyAsync("route",deny,first.Revision,default));
await Denied(()=>service.ApplyAsync("route",new string('é',20000),second.Revision,default));
await Denied(()=>service.ApplyAsync("../route",deny,second.Revision,default));
await Denied(()=>service.ApplyAsync("route",deny,"not-a-version",default));
var reader=new PolicyManagement(new("tenant-a","reader",["router:read","requests:read"]),store,dest,opa,"source-a");
await Denied(()=>reader.GetAsync(default));await Denied(()=>reader.ValidateAsync(deny,default));await Denied(()=>reader.PreviewAsync(deny,"pull_request",input,default));await Denied(()=>reader.ApplyAsync("route",deny,second.Revision,default));
Check(store.Writes==2);
using var canceled=new CancellationTokenSource();canceled.Cancel();
try{await service.ValidateAsync(deny,canceled.Token);throw new Exception("CANCEL_FAILED");}catch(OperationCanceledException){count++;}
Console.WriteLine($"PASS {count} policy management checks with real OPA; storage is a test double, no SQL/HTTP delivery");
class Destinations:IDestinationReader {public Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string tenant,CancellationToken ct)=>Task.FromResult<IReadOnlyList<RegisteredDestination>>([new("tenant-a","dest-a","review"),new("tenant-b","dest-b","review")]);}
class MemoryStore:IPolicyStore {
 public ManagedPolicy? Value;public int Writes;
 public Task<ManagedPolicy?> GetAsync(CancellationToken ct)=>Task.FromResult(Value);
 public Task<ManagedPolicy> ApplyAsync(string id,string source,string? expected,CancellationToken ct){
  if(Value is null?expected is not null:Value.Id!=id||Value.Revision!=expected)throw new InvalidOperationException("VERSION_CONFLICT");
  Value=new(id,source,(++Writes).ToString("x16"));return Task.FromResult(Value);
 }
}
