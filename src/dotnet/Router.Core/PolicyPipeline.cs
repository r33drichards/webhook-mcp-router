using System.Collections.Frozen;
using System.Text;
using System.Text.Json;
namespace Router.Core;

public sealed record DestinationRoute(string DestinationId,JsonElement Payload);
public sealed record PipelineContext(string TenantId,string SourceId,string Provider,string EventType);
public sealed record StageInput(PipelineContext Context,JsonElement Original,JsonElement Payload,IReadOnlyDictionary<string,JsonElement> Data,IReadOnlyList<RegisteredDestination> Destinations);
public sealed record StageOutput(bool Allow,JsonElement Data,JsonElement? Payload=null,IReadOnlyList<DestinationRoute>? Routes=null);
public interface IPolicyStage { Task<StageOutput> EvaluateAsync(StageInput input,CancellationToken ct); }
public sealed record OrderedStage(int Order,string Id,IPolicyStage Evaluator);
public sealed record RegisteredDestination(string TenantId,string Id,string Name="",string[]? Tags=null);
public interface IDestinationReader { Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string tenantId,CancellationToken ct); }
public sealed record PipelinePreview(bool Allowed,string Code,IReadOnlyList<DestinationRoute> Routes);

// Pure preview: no HTTP, SQL, secret resolution, activation or outbox writes.
// Only trusted bounded evaluator adapters may implement IPolicyStage. WaitAsync
// bounds caller latency, not CPU/memory of a malicious in-process implementation.
public sealed class PolicyPipeline {
    private readonly TenantContext tenant;private readonly OrderedStage[] stages;
    private readonly HashSet<string> destinations;private readonly RegisteredDestination[] metadata;
    public PolicyPipeline(TenantContext tenant,IEnumerable<OrderedStage> stages,IEnumerable<RegisteredDestination> destinations) {
        this.tenant=tenant;this.stages=stages.OrderBy(s=>s.Order).ToArray();
        if(this.stages.Length>16||this.stages.Any(s=>s.Order<0||!Identifier(s.Id))||this.stages.Select(s=>s.Order).Distinct().Count()!=this.stages.Length||this.stages.Select(s=>s.Id).Distinct(StringComparer.Ordinal).Count()!=this.stages.Length)throw new ArgumentException("PIPELINE_INVALID");
        metadata=destinations.Where(d=>d.TenantId==tenant.TenantId).OrderBy(d=>d.Id,StringComparer.Ordinal).Select(d=>d with{Tags=(d.Tags??[]).ToArray()}).ToArray();
        if(metadata.Any(d=>d.Name.Length>128||d.Tags!.Length>32||d.Tags.Any(t=>!Identifier(t))))throw new ArgumentException("DESTINATION_METADATA_INVALID");
        this.destinations=metadata.Select(d=>d.Id).ToHashSet(StringComparer.Ordinal);
        if(this.destinations.Count!=metadata.Length||this.destinations.Count>1024||this.destinations.Any(x=>!Identifier(x)))throw new ArgumentException("DESTINATION_REGISTRY_INVALID");
    }
    private static bool Identifier(string x)=>!string.IsNullOrEmpty(x)&&x.Length<=64&&x.All(c=>char.IsAsciiLetterOrDigit(c)||c is '_' or '-');
    private static JsonElement Copy(JsonElement value,int limit) {
        if(value.ValueKind==JsonValueKind.Undefined||Encoding.UTF8.GetByteCount(value.GetRawText())>limit)throw new InvalidOperationException("STAGE_DATA_LIMIT");
        return value.Clone();
    }
    public async Task<PipelinePreview> PreviewAsync(PipelineContext context,JsonElement body,CancellationToken ct=default) {
        tenant.Match(context.TenantId); // Context must come from authenticated source mapping.
        if(!Identifier(context.SourceId)||!Identifier(context.Provider)||!Identifier(context.EventType))throw new ArgumentException("CONTEXT_INVALID");
        if(stages.Length==0)return new(false,"DEFAULT_DENY",[]);
        using var budget=CancellationTokenSource.CreateLinkedTokenSource(ct);budget.CancelAfter(TimeSpan.FromSeconds(2));
        try {
            var original=Copy(body,65536);var payload=original;var data=new Dictionary<string,JsonElement>(StringComparer.Ordinal);
            for(int i=0;i<stages.Length;i++) {
                var stage=stages[i];using var deadline=CancellationTokenSource.CreateLinkedTokenSource(budget.Token);deadline.CancelAfter(TimeSpan.FromMilliseconds(600));
                var input=new StageInput(context,original,payload,data.ToFrozenDictionary(StringComparer.Ordinal),metadata.Select(d=>d with{Tags=d.Tags!.ToArray()}).ToArray());
                var output=await stage.Evaluator.EvaluateAsync(input,deadline.Token).WaitAsync(deadline.Token);
                if(!output.Allow)return new(false,"STAGE_DENIED",[]);
                data.Add(stage.Id,Copy(output.Data,8192));
                if(Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(data))>32768)return new(false,"STAGE_DATA_LIMIT",[]);
                if(output.Payload is JsonElement transformed)payload=Copy(transformed,32768);
                var routes=output.Routes??[];
                if(i!=stages.Length-1&&routes.Count!=0)return new(false,"EARLY_ROUTE_DENIED",[]);
                if(i==stages.Length-1) {
                    if(routes.Count is 0 or >16)return new(false,"DEFAULT_DENY",[]);
                    var ids=new HashSet<string>(StringComparer.Ordinal);var safe=new List<DestinationRoute>();
                    foreach(var route in routes) {
                        if(!destinations.Contains(route.DestinationId)||!ids.Add(route.DestinationId))return new(false,"DESTINATION_DENIED",[]);
                        safe.Add(new(route.DestinationId,Copy(route.Payload,8192)));
                    }
                    return new(true,"PREVIEW_ONLY",safe);
                }
            }
            return new(false,"DEFAULT_DENY",[]);
        }catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
        catch(OperationCanceledException){return new(false,"STAGE_TIMEOUT",[]);}
        catch{return new(false,"STAGE_ERROR",[]);}
    }
}

// Existing official OPA runtime, now with a generic destination_id result contract.
// Input contains previous stage data; provider-specific execution is not guessed.
public sealed class OpaRouteStage(OpaEvaluator evaluator,string policy,IReadOnlySet<string> registeredIds):IPolicyStage {
    public async Task<StageOutput> EvaluateAsync(StageInput input,CancellationToken ct) {
        string json=JsonSerializer.Serialize(new {schema_version=1,context=new {tenant_id=input.Context.TenantId,source_id=input.Context.SourceId,provider=input.Context.Provider,event_type=input.Context.EventType},original=input.Original,payload=input.Payload,enrichments=input.Data,destinations=input.Destinations.Select(d=>new {id=d.Id,name=d.Name,tags=d.Tags})});
        var routes=await evaluator.EvaluateDestinationsAsync(policy,json,registeredIds,ct);
        return new(routes.Count>0,JsonSerializer.SerializeToElement(new {matched=routes.Count>0}),Routes:routes);
    }
}

// Internal provider-neutral decision contract, NOT a claim about TypeSafe's wire API.
// Actual Jev/TypeSafe integration is deferred to issue #2. No provider calls here.
public sealed record DecisionResult(bool Allow,JsonElement Data);
public interface IDecisionProvider { Task<DecisionResult> DecideAsync(JsonElement approvedProjection,CancellationToken ct); }
public sealed class DecisionEnrichmentStage(IDecisionProvider provider,Func<StageInput,JsonElement> project):IPolicyStage {
    public async Task<StageOutput> EvaluateAsync(StageInput input,CancellationToken ct) {
        var projected=project(input);
        if(Encoding.UTF8.GetByteCount(projected.GetRawText())>8192)throw new InvalidOperationException("ENRICHMENT_INPUT_LIMIT");
        var result=await provider.DecideAsync(projected.Clone(),ct);
        if(result.Data.ValueKind!=JsonValueKind.Object||Encoding.UTF8.GetByteCount(result.Data.GetRawText())>8192)throw new InvalidOperationException("ENRICHMENT_RESULT_INVALID");
        return new(result.Allow,result.Data.Clone());
    }
}
