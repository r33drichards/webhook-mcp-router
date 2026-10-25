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
