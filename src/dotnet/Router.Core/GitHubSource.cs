using System.Text.Json;
namespace Router.Core;
public static class GitHubSource {
    // All GitHub event names are eligible for ingestion; no PR/action allowlist here.
    // No tenant derived from body. Caller authenticates raw bytes first.
    public static void ValidateVerified(JsonElement body,string eventType,string deliveryId,long repositoryId) {
        if(repositoryId<=0)throw new ArgumentException("SOURCE_CONFIG_INVALID");
        if(eventType.Length is 0 or >64||eventType.Any(c=>c!='_'&&(c<'a'||c>'z'))||!Guid.TryParseExact(deliveryId,"D",out _))throw new InvalidOperationException("GITHUB_INPUT_INVALID");
        try {
            Unique(body,0);
            if(body.GetProperty("repository").GetProperty("id").GetInt64()!=repositoryId)throw new InvalidOperationException("SOURCE_SCOPE_DENIED");
        }catch(Exception e)when(e is KeyNotFoundException or FormatException or OverflowException || e is InvalidOperationException && e.Message is not ("SOURCE_SCOPE_DENIED" or "GITHUB_INPUT_INVALID")){throw new InvalidOperationException("GITHUB_INPUT_INVALID");}
    }
    private static void Unique(JsonElement x,int depth) {
        if(depth>32)throw new InvalidOperationException("GITHUB_INPUT_INVALID");
        if(x.ValueKind==JsonValueKind.Object){var seen=new HashSet<string>(StringComparer.Ordinal);foreach(var p in x.EnumerateObject()){if(!seen.Add(p.Name))throw new InvalidOperationException("GITHUB_INPUT_INVALID");Unique(p.Value,depth+1);}}
        else if(x.ValueKind==JsonValueKind.Array)foreach(var item in x.EnumerateArray())Unique(item,depth+1);
    }
}
