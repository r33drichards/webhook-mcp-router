using System.Security.Cryptography;
using System.Text;
namespace Router.Core;

// Construct only after resolving a configured ingress source to a trusted tenant.
// Unknown sources must not instantiate this pipeline or write a tenant log.
public interface IIngressProcessor { Task<bool> AcceptAsync(string deliveryId,string eventType,byte[] body,string signature,CancellationToken ct=default); }
public sealed class LoggedIngress(IIngressProcessor ingestion,IRequestLog log,RequestCapture capture,byte[] sourceKey) {
    public async Task<bool> AcceptAsync(string deliveryId,string eventType,byte[] body,string signature,CancellationToken ct=default) {
        string expected="sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(sourceKey,body));
        bool verified=sourceKey.Length>=24 && CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(expected),Encoding.ASCII.GetBytes(signature));
        string outcome="failed";
        try {
            bool accepted=await ingestion.AcceptAsync(deliveryId,eventType,body,signature,ct);outcome=accepted?"accepted":"duplicate";return accepted;
        } catch(InvalidOperationException e) when(e.Message is "SIGNATURE_INVALID" or "INGRESS_LIMIT" or "SOURCE_SCOPE_DENIED" or "GITHUB_INPUT_INVALID") {outcome="rejected";throw;}
        finally {
            // Independent bounded cancellation permits logging a caller-cancelled failure.
            // If storage fails, surface failure rather than claiming the request log was persisted.
            using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(3));
            await log.AppendAsync(capture.Capture("POST",outcome,body,verified,eventType),deadline.Token);
        }
    }
}
