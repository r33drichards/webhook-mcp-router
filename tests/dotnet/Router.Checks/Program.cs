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
