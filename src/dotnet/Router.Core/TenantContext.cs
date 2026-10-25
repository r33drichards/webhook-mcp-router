using System.Collections.Frozen;
namespace Router.Core;

// Created only by trusted server composition/authentication, never deserialized from RPC input.
public sealed class TenantContext {
    public string TenantId { get; }
    public string ActorId { get; }
    private readonly FrozenSet<string> permissions;
    public TenantContext(string tenantId,string actorId,IEnumerable<string> scopes) {
        if(tenantId.Length is 0 or >64 || !tenantId.All(c=>char.IsAsciiLetterOrDigit(c)||c=='-'||c=='_'))throw new ArgumentException("TENANT_ID_INVALID");
        if(string.IsNullOrWhiteSpace(actorId))throw new ArgumentException("ACTOR_INVALID");
        TenantId=tenantId;ActorId=actorId;permissions=scopes.ToFrozenSet(StringComparer.Ordinal);
    }
    public void Demand(string scope) { if(!permissions.Contains(scope))throw new UnauthorizedAccessException("SCOPE_DENIED"); }
    public void Match(string tenant) { if(!string.Equals(TenantId,tenant,StringComparison.Ordinal))throw new UnauthorizedAccessException("TENANT_DENIED"); }
}
