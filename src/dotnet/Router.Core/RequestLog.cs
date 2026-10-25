using System.Text.Json;
using System.Text.Json.Nodes;
namespace Router.Core;

public sealed record CapturedRequest(string Id,DateTimeOffset Received,string Method,string Path,string Status,
    string CorrelationId,string Headers,string? Payload,bool Redacted,bool Truncated,bool ValidJson,bool Authenticated,string? EventType);
public sealed record RequestLogRow(long Sequence,CapturedRequest Request);
public sealed record RequestLogPage(IReadOnlyList<RequestLogRow> Items,long? NextBefore);
public interface IRequestLog {
    Task AppendAsync(CapturedRequest request,CancellationToken ct);
    Task<RequestLogPage> ListAsync(int limit,long? before,CancellationToken ct);
    Task<CapturedRequest?> FindAsync(string id,CancellationToken ct);
}
public sealed record CaptureOptions(int MaxInputBytes=65536,int MaxStoredBytes=8192,int RetentionDays=7,int MaxRows=10000,string[]? AdditionalRedactedFields=null);
public sealed class RequestCapture {
    private readonly CaptureOptions options;
    private readonly HashSet<string> secretFields;
    public RequestCapture(CaptureOptions? options=null) {
        this.options=options??new();
        if(this.options.MaxInputBytes is <1 or >65536||this.options.MaxStoredBytes is <128 or >8192||this.options.RetentionDays is <1 or >7||this.options.MaxRows is <1 or >10000)throw new ArgumentException("CAPTURE_LIMIT_INVALID");
        secretFields=new(new[]{"authorization","cookie","password","secret","token","credential","key","email","phone"}.Concat(this.options.AdditionalRedactedFields??[]),StringComparer.OrdinalIgnoreCase);
    }
    public CapturedRequest Capture(string method,string outcome,ReadOnlySpan<byte> body,bool authenticated,string? eventType=null) {
        if(outcome is not ("accepted" or "duplicate" or "rejected" or "failed"))throw new ArgumentException("LOG_STATUS_INVALID");
        // Raw paths, query strings, supplied IDs and arbitrary headers may contain secrets. Never persist them.
        string id=Guid.NewGuid().ToString("N");bool truncated=body.Length>options.MaxInputBytes,redacted=false,valid=false;string? payload=null;
        if(authenticated&&!truncated) {
            try {
                var node=JsonNode.Parse(body,documentOptions:new JsonDocumentOptions{MaxDepth=32});
                valid=true;if(node is JsonValue root && root.TryGetValue<string>(out _)){node=JsonValue.Create("[REDACTED]");redacted=true;}Sanitize(node,ref redacted);payload=node?.ToJsonString()??"null";
                if(System.Text.Encoding.UTF8.GetByteCount(payload)>options.MaxStoredBytes){payload=null;truncated=true;}
            } catch(JsonException){ /* Never retain malformed raw bytes: may contain credentials. */ }
        }
        // Event metadata is an enumerated provider value, not a free-form header copy.
        string? safeType=eventType is "push" or "pull_request" or "issues" or "ping"?eventType:null;
        return new(id,DateTimeOffset.UtcNow,method is "POST" or "GET"?method:"OTHER","/webhooks/{source}",outcome,id,"{}",payload,redacted,truncated,valid,authenticated,safeType);
    }
    private void Sanitize(JsonNode? node,ref bool redacted) {
        if(node is JsonObject obj) {
            foreach(var name in obj.Select(p=>p.Key).ToArray()) {
                // Property names can also contain credentials: only retain bounded identifier keys.
                if(name.Length>64||!name.All(c=>char.IsAsciiLetterOrDigit(c)||c=='_'||c=='-')){obj.Remove(name);redacted=true;continue;}
                if(secretFields.Any(s=>name.Contains(s,StringComparison.OrdinalIgnoreCase))||obj[name] is JsonValue v&&v.TryGetValue<string>(out _)){obj[name]="[REDACTED]";redacted=true;}
                else Sanitize(obj[name],ref redacted);
            }
        } else if(node is JsonArray array) {
            for(int i=0;i<array.Count;i++)if(array[i] is JsonValue v&&v.TryGetValue<string>(out _)){array[i]="[REDACTED]";redacted=true;}else Sanitize(array[i],ref redacted);
        }
    }
}
public sealed class RequestExplorer(TenantContext tenant,IRequestLog log) {
    public Task<RequestLogPage> ListAsync(int limit=25,long? before=null,CancellationToken ct=default){tenant.Demand("requests:read");if(limit is <1 or >100||before<=0)throw new ArgumentException("PAGE_INVALID");return log.ListAsync(limit,before,ct);}
    public Task<CapturedRequest?> DetailAsync(string id,CancellationToken ct=default){tenant.Demand("requests:read");return log.FindAsync(id,ct);}
    public async Task<object> ExampleAsync(string id,CancellationToken ct=default) {
        var request=await DetailAsync(id,ct)??throw new KeyNotFoundException("REQUEST_NOT_FOUND");
        if(!request.Authenticated||!request.ValidJson||request.Payload is null||request.Truncated)throw new InvalidOperationException("EXAMPLE_UNAVAILABLE");
        return new {untrustedData=true,requestId=id,redacted=request.Redacted,completeOriginal=false,input=new {provider="github",type=request.EventType,body=JsonSerializer.Deserialize<JsonElement>(request.Payload)}};
    }
}
