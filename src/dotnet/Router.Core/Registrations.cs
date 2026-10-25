using System.Text.Json;
namespace Router.Core;

// Owner is the trusted internal tenant ID, never RPC input.
// Stores bind a TenantContext and enforce it on every operation.
public sealed record Subscription(string Id, string Owner, string Name, string Arguments,
    string Callback, string KeyFingerprint, DateTimeOffset Expires);
public sealed record StoredPolicy(string Id, string Source);
public sealed record RegistrationSnapshot(IReadOnlyList<StoredPolicy> Policies, IReadOnlyList<Subscription> Subscriptions);
public sealed record PendingDelivery(string Id, string SubscriptionId, string Body);
public sealed record ClaimedDelivery(string Id, string SubscriptionId, string Body, Guid Lease, int Attempt);

public interface IRegistrationReader {
    Task<RegistrationSnapshot> SnapshotAsync(string owner, CancellationToken ct);
}
public interface IRegistrationWriter {
    Task SaveSubscriptionAsync(Subscription value, CancellationToken ct);
    Task DeleteSubscriptionAsync(string owner, string id, CancellationToken ct);
    Task SavePolicyAsync(string owner, StoredPolicy policy, CancellationToken ct);
}
public interface IOutbox {
    Task<bool> AcceptAsync(string source, string deliveryId, string bodyHash, IReadOnlyList<PendingDelivery> deliveries, CancellationToken ct);
    Task<ClaimedDelivery?> ClaimAsync(TimeSpan leaseTime, CancellationToken ct);
    Task<bool> CompleteAsync(string id, Guid lease, CancellationToken ct);
    Task<bool> RetryAsync(string id, Guid lease, TimeSpan delay, int maxAttempts, CancellationToken ct);
}
