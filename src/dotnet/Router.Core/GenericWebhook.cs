using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
namespace Router.Core;

public sealed class GenericIngestion(IRegistrationReader policies,IDestinationReader destinations,IOutbox outbox,OpaEvaluator opa,TenantContext tenant,byte[] ingressKey,string sourceId,long repositoryId):IIngressProcessor {
    public async Task<bool> AcceptAsync(string deliveryId,string eventType,byte[] body,string signature,CancellationToken ct=default) {
        if(body.Length>65536||deliveryId.Length is 0 or >128||eventType.Length is 0 or >64)throw new InvalidOperationException("INGRESS_LIMIT");
        string expected="sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(ingressKey,body));
        if(ingressKey.Length<24||!CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(expected),Encoding.ASCII.GetBytes(signature)))throw new InvalidOperationException("SIGNATURE_INVALID");
        using var parsed=JsonDocument.Parse(body);GitHubSource.ValidateVerified(parsed.RootElement,eventType,deliveryId,repositoryId);
        var snapshot=await policies.SnapshotAsync(tenant.TenantId,ct);
        // First slice: one explicit routing policy; no implicit union or ordering guesses.
        if(snapshot.Policies.Count>1)throw new InvalidOperationException("GENERIC_POLICY_CONFIGURATION");
        var metadata=await destinations.SnapshotAsync(tenant.TenantId,ct);
        var ids=metadata.Where(d=>d.TenantId==tenant.TenantId).Select(d=>d.Id).ToHashSet(StringComparer.Ordinal);
        OrderedStage[] stages=snapshot.Policies.Select(p=>new OrderedStage(100,"route",new OpaRouteStage(opa,p.Source,ids))).ToArray();
        var preview=await new PolicyPipeline(tenant,stages,metadata).PreviewAsync(new(tenant.TenantId,sourceId,"github",eventType),parsed.RootElement,ct);
        // Policy deny/error/timeout produces no deliveries. Receipt still records this decision.
        var selected=preview.Allowed?preview.Routes:[];
        var deliveries=selected.Select(r=>new PendingDelivery("wh_"+Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(tenant.TenantId+":"+sourceId+":"+deliveryId+":"+r.DestinationId))),r.DestinationId,r.Payload.GetRawText())).ToArray();
        return await outbox.AcceptAsync(sourceId,deliveryId,Convert.ToHexStringLower(SHA256.HashData(body)),deliveries,ct);
    }
}

// Protected configuration is never part of RegisteredDestination/OPA input.
public sealed record ProtectedDestination(string Id,Uri Endpoint,string SigningKeyReference);
public interface IDestinationResolver { Task<ProtectedDestination?> ResolveAsync(string tenantId,string id,CancellationToken ct); }
// Resolver returns a fresh owned buffer; processor clears it after each attempt.
public interface IDeliverySecretResolver { Task<byte[]> ResolveAsync(string reference,CancellationToken ct); }
public interface IWebhookTransport { Task<bool> SendAsync(Uri endpoint,string eventId,byte[] payload,byte[] signingKey,CancellationToken ct); }
public sealed class GenericDeliveryProcessor(IDestinationResolver destinations,IDeliverySecretResolver secrets,IOutbox outbox,TenantContext tenant,IWebhookTransport transport) {
    public async Task<bool> OnceAsync(CancellationToken ct=default) {
        var item=await outbox.ClaimAsync(TimeSpan.FromSeconds(30),ct);if(item is null)return false;
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(10));
        byte[]? key=null;
        try {
            var target=await destinations.ResolveAsync(tenant.TenantId,item.SubscriptionId,deadline.Token);
            if(target is null||target.Id!=item.SubscriptionId){await outbox.RetryAsync(item.Id,item.Lease,TimeSpan.Zero,1,ct);return true;}
            SafeWebhookTransport.ValidateEndpoint(target.Endpoint);
            key=await secrets.ResolveAsync(target.SigningKeyReference,deadline.Token);
            if(key.Length is <24 or >64)throw new InvalidOperationException("DELIVERY_KEY_INVALID");
            byte[] body=Encoding.UTF8.GetBytes(item.Body);if(body.Length>65536)throw new InvalidOperationException("DELIVERY_BODY_LIMIT");
            if(await transport.SendAsync(target.Endpoint,item.Id,body,key,deadline.Token)){await outbox.CompleteAsync(item.Id,item.Lease,ct);return true;}
        }catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
        catch { /* No target/auth/body/exception logging. Durable bounded retry below. */ }
        finally {if(key is not null)CryptographicOperations.ZeroMemory(key);}
        await outbox.RetryAsync(item.Id,item.Lease,TimeSpan.FromSeconds(Math.Min(300,Math.Pow(2,item.Attempt))),5,ct);return true;
    }
}
