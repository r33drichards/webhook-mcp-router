using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
namespace Router.Core;

public sealed class Ingestion(IRegistrationReader registrations,IOutbox outbox,OpaEvaluator evaluator,TenantContext tenant,byte[] ingressKey,GitHubPullRequestScope? pullRequestScope=null,string sourceId="github") {
    public async Task<bool> AcceptAsync(string deliveryId,string eventType,byte[] rawBody,string signature,CancellationToken ct=default) {
        if(rawBody.Length>65536 || deliveryId.Length is 0 or >128 || eventType.Length is 0 or >64)throw new InvalidOperationException("INGRESS_LIMIT");
        string expected="sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(ingressKey,rawBody));
        if(ingressKey.Length<24 || !CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(expected),Encoding.ASCII.GetBytes(signature)))throw new InvalidOperationException("SIGNATURE_INVALID");
        using var body=JsonDocument.Parse(rawBody);
        if(pullRequestScope is not null)_=GitHubPullRequest.ValidateVerified(body.RootElement,eventType,deliveryId,pullRequestScope);
        var snapshot=await registrations.SnapshotAsync(tenant.TenantId,ct);
        if(snapshot.Policies.Count>64||snapshot.Subscriptions.Count>1024)throw new InvalidOperationException("REGISTRY_LIMIT");
        var ids=snapshot.Subscriptions.Select(s=>s.Id).ToHashSet(StringComparer.Ordinal);
        string input=JsonSerializer.Serialize(new {provider="github",type=eventType,body=body.RootElement});
        var selected=new Dictionary<string,Route>(StringComparer.Ordinal);
        foreach(var p in snapshot.Policies.OrderBy(p=>p.Id,StringComparer.Ordinal)) {
            try { foreach(var route in await evaluator.EvaluateAsync(p.Source,input,ids,ct))selected.TryAdd(route.SubscriptionId,route); }
            catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
            catch { /* per-policy isolation; do not log policy/input/exception */ }
        }
        var deliveries=selected.Values.Select(route=> {
            string id="evt_"+Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(tenant.TenantId+":"+sourceId+":"+deliveryId+":"+route.SubscriptionId)));
            return new PendingDelivery(id,route.SubscriptionId,JsonSerializer.Serialize(new {eventId=id,name=EventService.EventName,timestamp=DateTimeOffset.UtcNow.ToString("O"),data=route.Payload,cursor=(string?)null}));
        }).ToArray();
        return await outbox.AcceptAsync(sourceId,deliveryId,Convert.ToHexStringLower(SHA256.HashData(rawBody)),deliveries,ct);
    }
}

public sealed class DeliveryProcessor(IRegistrationReader registrations,IOutbox outbox,TenantContext tenant,string callback,byte[] key,HttpClient http) {
    public async Task<bool> OnceAsync(CancellationToken ct=default) {
        var item=await outbox.ClaimAsync(TimeSpan.FromSeconds(30),ct);if(item is null)return false;
        var snapshot=await registrations.SnapshotAsync(tenant.TenantId,ct);
        var sub=snapshot.Subscriptions.SingleOrDefault(s=>s.Id==item.SubscriptionId);
        if(sub is null||sub.Callback!=callback||sub.KeyFingerprint!=EventService.Fingerprint(key)) {
            await outbox.RetryAsync(item.Id,item.Lease,TimeSpan.Zero,1,ct);return true;
        }
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(10));
        try {
            using var request=EventService.SignedRequest(callback,key,sub.Id,item.Id,item.Body);
            using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);
            if(response.IsSuccessStatusCode){await outbox.CompleteAsync(item.Id,item.Lease,ct);return true;}
        } catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
        catch(HttpRequestException) {} catch(OperationCanceledException) {}
        await outbox.RetryAsync(item.Id,item.Lease,TimeSpan.FromSeconds(Math.Min(300,Math.Pow(2,item.Attempt))),5,ct);return true;
    }
}
