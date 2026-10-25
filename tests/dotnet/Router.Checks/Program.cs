using System.Text.Json;
using Router.Core;

if (args.Length != 2) throw new ArgumentException("Supply absolute OPA executable and capabilities paths");
var evaluator = new OpaEvaluator(args[0], args[1]);
const string policy = """
package router
import rego.v1
default routes := []
routes := [{"subscription_id":"sub_test", "payload":{"kind":"synthetic"}}] if { input.action == "opened" }
""";
var registered = new HashSet<string> { "sub_test" };
void Check(bool condition, string name) { if (!condition) throw new Exception(name); Console.WriteLine("PASS " + name); }
async Task Reject(string source, string input, IReadOnlySet<string> ids, string name) {
 try { await evaluator.EvaluateAsync(source, input, ids); } catch { Console.WriteLine("PASS " + name); return; }
 throw new Exception("Unexpected acceptance: " + name);
}
var routes = await evaluator.EvaluateAsync(policy, "{\"action\":\"opened\"}", registered);
Check(routes.Count == 1 && routes[0].SubscriptionId == "sub_test", "native OPA match");
Check((await evaluator.EvaluateAsync(policy, "{\"action\":\"closed\"}", registered)).Count == 0, "nonmatch");
await Reject(policy, "{\"action\":\"opened\"}", new HashSet<string>(), "unknown ID rejected");
await Reject("package router\nroutes := http.send({\"method\":\"GET\",\"url\":\"https://example.invalid\"})", "{}", registered, "network builtin rejected");
await Reject("package router\nroutes := [", "{}", registered, "malformed policy rejected");
await Reject(policy, "not-json", registered, "malformed input rejected");
var concurrent = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => evaluator.EvaluateAsync(policy, "{\"action\":\"opened\"}", registered)));
Check(concurrent.All(x => x.Count == 1), "concurrent temp-file isolation");
Check(UsageThresholds.Crossed(799999, 0).Count == 0, "execution below threshold");
Check(UsageThresholds.Crossed(800000, 0).SequenceEqual(new[]{80}), "execution 80 percent");
Check(UsageThresholds.Crossed(0, 368640000000m).SequenceEqual(new[]{80,90}), "units 90 percent conversion");
Check(UsageThresholds.Crossed(1000000, 409600000000m).SequenceEqual(new[]{80,90,100}), "full free grant thresholds");

await Reject("package router\nroutes := [{\"subscription_id\":\"sub_test\",\"payload\":{},\"url\":\"https://example.invalid\"}]", "{}", registered, "arbitrary destination URL rejected");
using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
try { await evaluator.EvaluateAsync(policy, "{}", registered, cancelled.Token); throw new Exception("cancel not honored"); }
catch (OperationCanceledException) { Console.WriteLine("PASS cancellation"); }

// Synthetic provider contract; no real repository or webhook registration.
const string prJson="""{"repository":{"id":100},"action":"opened","number":7,"pull_request":{"id":200,"number":7,"draft":false,"merged":false}}""";
var prScope=new GitHubPullRequestScope(100,["opened","closed"]);
const string delivery="00000000-0000-0000-0000-000000000001";
GitHubPullRequestInput Pr(string json,string type="pull_request",string id=delivery) {
 using var doc=System.Text.Json.JsonDocument.Parse(json);
 return GitHubPullRequest.ValidateVerified(doc.RootElement,type,id,prScope);
}
void PrReject(string json,string label,string type="pull_request",string id=delivery) {
 try{_=Pr(json,type,id);}catch(InvalidOperationException){Console.WriteLine("PASS "+label);return;}
 throw new Exception(label);
}
Check(Pr(prJson).Number==7,"typed PR shape accepted");
Check(Pr(prJson.Replace("\"merged\":false","\"merged\":null")).Merged is null,"nullable GitHub merged field accepted");
PrReject(prJson.Replace("\"id\":100","\"id\":101"),"wrong repository denied");
PrReject(prJson.Replace("opened","edited"),"unselected action denied");
PrReject(prJson,"wrong event denied","push");
PrReject(prJson,"invalid delivery GUID denied",id:"not-guid");
PrReject(prJson.Replace("\"number\":7,\"draft\"","\"number\":8,\"draft\""),"mismatched PR number denied");
PrReject(prJson.Replace("\"draft\":false","\"draft\":\"false\""),"wrong PR field type denied");
PrReject(prJson.Replace("\"action\":\"opened\"","\"action\":\"opened\",\"action\":\"closed\""),"duplicate property denied");
PrReject(prJson.Replace("\"id\":100","\"id\":9223372036854775808"),"repository numeric overflow denied");
PrReject("null","nonobject PR denied");
try{GitHubPullRequest.ValidateScope(new(100,[]));throw new Exception("Empty action scope accepted");}catch(ArgumentException){Console.WriteLine("PASS empty action scope denied");}

var ingressKey=Enumerable.Repeat((byte)7,32).ToArray();
var registry=new EmptyRegistry();var receipt=new CaptureOutbox();var logger=new CaptureLog();
var typedIngress=new LoggedIngress(new Ingestion(registry,receipt,evaluator,new TenantContext("tenant-test","test",[]),ingressKey,prScope,"source-test"),logger,new RequestCapture(),ingressKey);
byte[] Bytes(string s)=>System.Text.Encoding.UTF8.GetBytes(s);
string Sign(byte[] raw)=>"sha256="+Convert.ToHexStringLower(System.Security.Cryptography.HMACSHA256.HashData(ingressKey,raw));
async Task IngressReject(byte[] raw,string signature,string expected,string label) {
 try{await typedIngress.AcceptAsync(delivery,"pull_request",raw,signature);}catch(InvalidOperationException e)when(e.Message==expected){Console.WriteLine("PASS "+label);return;}
 throw new Exception(label);
}
await IngressReject(Bytes("not-json"),"sha256=bad","SIGNATURE_INVALID","signature checked before PR parsing");
Check(logger.Last is {Authenticated:false,Payload:null,Status:"rejected"}&&registry.Reads==0,"invalid signature neither evaluated nor retained");
var wrongRepo=Bytes(prJson.Replace("\"id\":100","\"id\":101"));
await IngressReject(wrongRepo,Sign(wrongRepo),"SOURCE_SCOPE_DENIED","verified wrong repository rejected before policy evaluation");
Check(logger.Last is {Authenticated:true,Redacted:true,Status:"rejected"}&&registry.Reads==0,"attributable rejection log redacted and policy untouched");
var validPr=Bytes(prJson);
Check(await typedIngress.AcceptAsync(delivery,"pull_request",validPr,Sign(validPr)),"verified scoped PR accepted");
Check(receipt.Source=="source-test"&&registry.Reads==1,"configured source propagated to receipt storage");
Check(!await typedIngress.AcceptAsync(delivery,"pull_request",validPr,Sign(validPr))&&logger.Last?.Status=="duplicate","duplicate receipt separately logged");


// Generic webhook pipeline preview, not an HTTP callback or a real model call.
JsonElement Json(string text)=>JsonDocument.Parse(text).RootElement.Clone();
var ctx=new PipelineContext("tenant-test","mcp-js-github","github","pull_request");
var tenantForPipeline=new TenantContext("tenant-test","test",[]);
var destinations=new[]{new RegisteredDestination("tenant-test","review_destination")};
const string reviewBody="""{"repository":{"id":961207108,"full_name":"r33drichards/mcp-js"},"action":"labeled","label":{"name":"review"},"pull_request":{"number":7,"title":"never send this to enrichment"}}""";
const string reviewPolicy="""
package router
import rego.v1
default routes := []
routes := [{"destination_id":"review_destination","payload":input.payload}] if {
 input.context.provider == "github"
 input.context.event_type == "pull_request"
 input.original.repository.id == 961207108
 input.original.repository.full_name == "r33drichards/mcp-js"
 input.original.action == "labeled"
 input.original.label.name == "review"
}
""";
var routeStage=new OpaRouteStage(evaluator,reviewPolicy,new HashSet<string>{"review_destination"});
PolicyPipeline Pipeline(params OrderedStage[] stages)=>new(tenantForPipeline,stages,destinations);
var reviewPipeline=Pipeline(new OrderedStage(100,"route",routeStage));
Check(!(await Pipeline().PreviewAsync(ctx,Json(reviewBody))).Allowed,"empty pipeline defaults deny");
Check((await reviewPipeline.PreviewAsync(ctx,Json(reviewBody))).Allowed,"generic newly-added review label matches");
foreach(var (body,label) in new[]{(reviewBody.Replace("961207108","961207109"),"unrelated repository denied"),(reviewBody.Replace("\"review\"","\"Review\""),"label exact case required"),(reviewBody.Replace("labeled","opened"),"PR action must be labeled"),(reviewBody.Replace("\"label\":{\"name\":\"review\"}","\"labels\":[{\"name\":\"review\"}]"),"existing label list does not imply newly added label")})
 Check(!(await reviewPipeline.PreviewAsync(ctx,Json(body))).Allowed,label);
Check(!(await reviewPipeline.PreviewAsync(ctx with{EventType="issues"},Json(reviewBody))).Allowed,"unrelated event ingested but not forwarded");
var foreign=new PolicyPipeline(tenantForPipeline,[new(100,"route",routeStage)],[new("other-tenant","review_destination")]);
Check(!(await foreign.PreviewAsync(ctx,Json(reviewBody))).Allowed,"generic destination belongs to trusted tenant");
try{await reviewPipeline.PreviewAsync(ctx with{TenantId="other-tenant"},Json(reviewBody));throw new Exception("tenant spoof accepted");}catch(UnauthorizedAccessException){Console.WriteLine("PASS pipeline context tenant spoof denied");}
foreach(var eventName in new[]{"push","release","issues","pull_request_review","ping"}) {
 GitHubSource.ValidateVerified(Json(reviewBody),eventName,delivery,961207108);
 Console.WriteLine("PASS generic source admits "+eventName);
}
var model=new SyntheticDecisionProvider();
var enrichment=new DecisionEnrichmentStage(model,input=>JsonSerializer.SerializeToElement(new{repository_id=input.Original.GetProperty("repository").GetProperty("id").GetInt64(),number=input.Original.GetProperty("pull_request").GetProperty("number").GetInt32()}));
var transform=new SyntheticStage((input,ct)=>Task.FromResult(new StageOutput(true,Json("{}"),Json("{\"number\":7}"))));
const string enrichedPolicy="""
package router
import rego.v1
default routes := []
routes := [{"destination_id":"review_destination","payload":input.payload}] if { input.enrichments.assess.approved == true; input.payload.number == 7 }
""";
var enriched=Pipeline(new(100,"route",new OpaRouteStage(evaluator,enrichedPolicy,new HashSet<string>{"review_destination"})),new(20,"transform",transform),new(10,"assess",enrichment));
var enrichedPreview=await enriched.PreviewAsync(ctx,Json(reviewBody));
Check(enrichedPreview.Allowed&&enrichedPreview.Routes.Single().Payload.GetProperty("number").GetInt32()==7&&enrichedPreview.Routes.Single().Payload.EnumerateObject().Count()==1,"ordered enrichment data consumed by OPA and payload transformed");
Check(model.Last is not null&&!model.Last.Contains("title")&&!model.Last.Contains("never send"),"external-adapter boundary receives approved projection only");
var denied=new SyntheticStage((input,ct)=>Task.FromResult(new StageOutput(false,Json("{}"))));
Check(!(await Pipeline(new(10,"deny",denied),new(100,"route",routeStage)).PreviewAsync(ctx,Json(reviewBody))).Allowed,"denied stage cannot route");
var error=new SyntheticStage((input,ct)=>throw new InvalidOperationException("synthetic-private-message"));
Check((await Pipeline(new(10,"error",error),new(100,"route",routeStage)).PreviewAsync(ctx,Json(reviewBody))).Code=="STAGE_ERROR","error stage fails closed without exposing exception");
var slow=new SyntheticStage(async(input,ct)=>{await Task.Delay(5000,ct);return new(true,Json("{}"));});
Check((await Pipeline(new(10,"slow",slow),new(100,"route",routeStage)).PreviewAsync(ctx,Json(reviewBody))).Code=="STAGE_TIMEOUT","stage deadline denies forwarding");


var metadataDestinations=new[]{new RegisteredDestination("tenant-test","dest_one","Review team",["review"]),new RegisteredDestination("tenant-test","dest_two","Other team",["other"]),new RegisteredDestination("foreign","dest_foreign","Secret foreign name",["review"])};
const string metadataPolicy="""
package router
import rego.v1
routes := [{"destination_id":d.id,"payload":input.payload} | d := input.destinations[_]; d.tags[_] == "review"]
""";
var metadataPipeline=new PolicyPipeline(tenantForPipeline,[new(100,"route",new OpaRouteStage(evaluator,metadataPolicy,new HashSet<string>{"dest_one","dest_two","dest_foreign"}))],metadataDestinations);
var metaResult=await metadataPipeline.PreviewAsync(ctx,Json(reviewBody));
Check(metaResult.Allowed&&metaResult.Routes.Select(r=>r.DestinationId).SequenceEqual(new[]{"dest_one"}),"OPA selects tenant-scoped metadata by tag without URLs");
var trialPolicy=File.ReadAllText(Path.Combine(Path.GetDirectoryName(args[1])!,"trial","mcp-js-review.rego"));
var trialPipeline=new PolicyPipeline(tenantForPipeline,[new(100,"trial",new OpaRouteStage(evaluator,trialPolicy,new HashSet<string>{"dest_one","dest_two"}))],metadataDestinations);
Check((await trialPipeline.PreviewAsync(ctx,Json(reviewBody))).Routes.Single().DestinationId=="dest_one","actual trial policy selects database review tag");
Check(!(await trialPipeline.PreviewAsync(ctx with{EventType="push"},Json(reviewBody))).Allowed,"actual trial policy defaults deny other events");


foreach(var address in new[]{"127.0.0.1","10.0.0.1","169.254.169.254","192.168.1.1","100.64.0.1","198.18.0.1","203.0.113.1","::1","::ffff:127.0.0.1","fe80::1","fc00::1","2001:db8::1","2002:7f00:1::1","3fff::1"})
 Check(!SafeWebhookTransport.IsPublic(System.Net.IPAddress.Parse(address)),"SSRF address denied "+address);
Check(SafeWebhookTransport.IsPublic(System.Net.IPAddress.Parse("1.1.1.1"))&&SafeWebhookTransport.IsPublic(System.Net.IPAddress.Parse("2606:4700:4700::1111")),"public IPv4 and IPv6 recognized without connecting");
foreach(var endpoint in new[]{"http://example.invalid","https://127.0.0.1","https://example.invalid:444","https://user:pass@example.invalid","https://example.invalid/?token=fixture","https://example.invalid/#fragment"}) {
 try{SafeWebhookTransport.ValidateEndpoint(new Uri(endpoint));throw new Exception("unsafe URL accepted");}catch(InvalidOperationException){Console.WriteLine("PASS prohibited destination URL form");}
}
using(var signed=SafeWebhookTransport.CreateSignedRequest(new Uri("https://sink.example.invalid/hook"),"wh_synthetic",Bytes("{}"),ingressKey)) {
 Check(signed.Headers.GetValues("X-Webhook-Signature-256").Single()==Sign(Bytes("{}")),"generic callback HMAC covers exact output bytes");
 Check(signed.Headers.GetValues("X-Webhook-Delivery").Single()=="wh_synthetic","generic callback stable delivery header");
}
var genericStore=new MemoryWebhookOutbox();var genericRegistry=new FixedPolicyReader(trialPolicy);var genericMetadata=new FixedDestinationReader(metadataDestinations.Where(d=>d.TenantId=="tenant-test").ToArray());
var genericIngress=new GenericIngestion(genericRegistry,genericMetadata,genericStore,evaluator,tenantForPipeline,ingressKey,"mcp-js-github",961207108);
var reviewBytes=Bytes(reviewBody);
Check(await genericIngress.AcceptAsync(delivery,"pull_request",reviewBytes,Sign(reviewBytes)),"generic ingress evaluates selected OPA policy and queues");
Check(genericStore.Pending!.SubscriptionId=="dest_one"&&Json(genericStore.Pending.Body).GetProperty("action").GetString()=="labeled","generic queue contains destination ID and payload, no MCP envelope");
Check(!await genericIngress.AcceptAsync(delivery,"pull_request",reviewBytes,Sign(reviewBytes)),"generic ingress duplicate receipt does not duplicate queue");
var emptyStore=new MemoryWebhookOutbox();
await new GenericIngestion(new EmptyRegistry(),genericMetadata,emptyStore,evaluator,tenantForPipeline,ingressKey,"mcp-js-github",961207108).AcceptAsync(delivery,"push",reviewBytes,Sign(reviewBytes));
Check(emptyStore.Pending is null,"all-event ingestion with no policy records receipt but never forwards");
var resolver=new FixedProtectedResolver();var secretProvider=new SyntheticSecrets();var deliveryTransport=new SyntheticWebhookTransport();
Check(await new GenericDeliveryProcessor(resolver,secretProvider,genericStore,tenantForPipeline,deliveryTransport).OnceAsync(),"generic dispatcher consumes queued destination");
Check(genericStore.Completed&&deliveryTransport.Calls==1&&resolver.LastTenant=="tenant-test"&&secretProvider.Buffer!.All(b=>b==0),"private destination resolution scoped; success completes and secret buffer cleared");
var retryStore=new MemoryWebhookOutbox();await retryStore.AcceptAsync("source","id",new string('a',64),[new("wh_failure","dest_one","{}")],default);
var failingTransport=new SyntheticWebhookTransport{Success=false};
await new GenericDeliveryProcessor(resolver,new SyntheticSecrets(),retryStore,tenantForPipeline,failingTransport).OnceAsync();
Check(retryStore.Retried&&!retryStore.Completed,"generic delivery failure uses bounded durable retry");

Check((await trialPipeline.PreviewAsync(ctx,Json(reviewBody.Replace("never send this to enrichment",new string('x',16000))))).Allowed,"bounded generic payload above log limit remains deliverable");
sealed class EmptyRegistry:IRegistrationReader {
 public int Reads;
 public Task<RegistrationSnapshot> SnapshotAsync(string owner,CancellationToken ct){Reads++;return Task.FromResult(new RegistrationSnapshot([],[]));}
}
sealed class CaptureOutbox:IOutbox {
 public string? Source;private readonly HashSet<string> seen=[];
 public Task<bool> AcceptAsync(string source,string id,string hash,IReadOnlyList<PendingDelivery> deliveries,CancellationToken ct){Source=source;return Task.FromResult(seen.Add(source+":"+id));}
 public Task<ClaimedDelivery?> ClaimAsync(TimeSpan lease,CancellationToken ct)=>throw new NotSupportedException();
 public Task<bool> CompleteAsync(string id,Guid lease,CancellationToken ct)=>throw new NotSupportedException();
 public Task<bool> RetryAsync(string id,Guid lease,TimeSpan delay,int max,CancellationToken ct)=>throw new NotSupportedException();
}
sealed class CaptureLog:IRequestLog {
 public CapturedRequest? Last;
 public Task AppendAsync(CapturedRequest request,CancellationToken ct){Last=request;return Task.CompletedTask;}
 public Task<RequestLogPage> ListAsync(int limit,long? before,CancellationToken ct)=>throw new NotSupportedException();
 public Task<CapturedRequest?> FindAsync(string id,CancellationToken ct)=>throw new NotSupportedException();
}

sealed class SyntheticStage(Func<StageInput,CancellationToken,Task<StageOutput>> run):IPolicyStage {
 public Task<StageOutput> EvaluateAsync(StageInput input,CancellationToken ct)=>run(input,ct);
}
sealed class SyntheticDecisionProvider:IDecisionProvider {
 public string? Last;
 public Task<DecisionResult> DecideAsync(JsonElement projection,CancellationToken ct){Last=projection.GetRawText();return Task.FromResult(new DecisionResult(true,JsonSerializer.SerializeToElement(new{approved=true})));}
}

sealed class FixedPolicyReader(string source):IRegistrationReader {
 public Task<RegistrationSnapshot> SnapshotAsync(string owner,CancellationToken ct)=>Task.FromResult(new RegistrationSnapshot([new("trial",source)],[]));
}
sealed class FixedDestinationReader(IReadOnlyList<RegisteredDestination> values):IDestinationReader {
 public Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string tenantId,CancellationToken ct)=>Task.FromResult(values);
}
sealed class MemoryWebhookOutbox:IOutbox {
 public PendingDelivery? Pending;public bool Completed,Retried;private bool accepted;
 public Task<bool> AcceptAsync(string source,string id,string hash,IReadOnlyList<PendingDelivery> deliveries,CancellationToken ct){if(accepted)return Task.FromResult(false);accepted=true;Pending=deliveries.SingleOrDefault();return Task.FromResult(true);}
 public Task<ClaimedDelivery?> ClaimAsync(TimeSpan lease,CancellationToken ct)=>Task.FromResult(Pending is null?null:new ClaimedDelivery(Pending.Id,Pending.SubscriptionId,Pending.Body,Guid.NewGuid(),1));
 public Task<bool> CompleteAsync(string id,Guid lease,CancellationToken ct){Completed=true;return Task.FromResult(true);}
 public Task<bool> RetryAsync(string id,Guid lease,TimeSpan delay,int max,CancellationToken ct){Retried=true;return Task.FromResult(true);}
}
sealed class FixedProtectedResolver:IDestinationResolver {
 public string? LastTenant;
 public Task<ProtectedDestination?> ResolveAsync(string tenantId,string id,CancellationToken ct){LastTenant=tenantId;return Task.FromResult<ProtectedDestination?>(new(id,new Uri("https://sink.example.invalid/hook"),"synthetic-key-ref"));}
}
sealed class SyntheticSecrets:IDeliverySecretResolver {
 public byte[]? Buffer;
 public Task<byte[]> ResolveAsync(string reference,CancellationToken ct){Buffer=Enumerable.Repeat((byte)9,32).ToArray();return Task.FromResult(Buffer);}
}
sealed class SyntheticWebhookTransport:IWebhookTransport {
 public bool Success=true;public int Calls;
 public Task<bool> SendAsync(Uri endpoint,string id,byte[] payload,byte[] key,CancellationToken ct){Calls++;return Task.FromResult(Success);}
}
