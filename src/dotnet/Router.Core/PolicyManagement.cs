using System.Text;
using System.Text.Json;
namespace Router.Core;

// Policies are tenant-owned, not client-owned: authorized collaborators share one
// active generic routing policy. Revision is an opaque SQL rowversion, never time.
public sealed record ManagedPolicy(string Id,string Source,string Revision);
public interface IPolicyStore {
    Task<ManagedPolicy?> GetAsync(CancellationToken ct);
    Task<ManagedPolicy> ApplyAsync(string id,string source,string? expectedRevision,CancellationToken ct);
}
public sealed class PolicyManagement(TenantContext tenant,IPolicyStore store,IDestinationReader destinations,OpaEvaluator opa,string sourceId) {
    public Task<ManagedPolicy?> GetAsync(CancellationToken ct){tenant.Demand("policies:read");return store.GetAsync(ct);}
    public async Task<object> ValidateAsync(string source,CancellationToken ct){tenant.Demand("policies:test");Source(source);await opa.ValidateAsync(source,ct);return new{valid=true,activation=false,contract="data.router.routes -> [{destination_id,payload}]"};}
    public async Task<PipelinePreview> PreviewAsync(string source,string eventType,JsonElement input,CancellationToken ct){
        tenant.Demand("policies:test");Source(source);
        if(input.ValueKind!=JsonValueKind.Object||Encoding.UTF8.GetByteCount(input.GetRawText())>65536)throw new ArgumentException("INPUT_LIMIT");
        await opa.ValidateAsync(source,ct);
        var metadata=await destinations.SnapshotAsync(tenant.TenantId,ct);
        var ids=metadata.Where(d=>d.TenantId==tenant.TenantId).Select(d=>d.Id).ToHashSet(StringComparer.Ordinal);
        return await new PolicyPipeline(tenant,[new(100,"route",new OpaRouteStage(opa,source,ids))],metadata).PreviewAsync(new(tenant.TenantId,sourceId,"github",eventType),input,ct);
    }
    // Deliberately explicit apply: changes the policy used by subsequent ingress.
    // Does not enable dispatch, create destinations or change auth/credentials.
    public async Task<ManagedPolicy> ApplyAsync(string id,string source,string? expectedRevision,CancellationToken ct){
        tenant.Demand("policies:write");Identifier(id);Source(source);Revision(expectedRevision);
        await opa.ValidateAsync(source,ct);
        return await store.ApplyAsync(id,source,expectedRevision,ct);
    }
    public static void Identifier(string id){if(id.Length is 0 or >64||id.Any(c=>!char.IsAsciiLetterOrDigit(c)&&c is not ('_' or '-')))throw new ArgumentException("POLICY_ID_INVALID");}
    public static void Source(string source){if(Encoding.UTF8.GetByteCount(source) is 0 or >32768)throw new ArgumentException("POLICY_LIMIT");}
    public static void Revision(string? value){if(value is not null&&(value.Length!=16||value.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))))throw new ArgumentException("REVISION_INVALID");}
}
