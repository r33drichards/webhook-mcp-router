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
