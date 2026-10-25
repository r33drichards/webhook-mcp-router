using System.Text.Json;
namespace Router.Core;

// Operator-owned scope, never supplied by webhook JSON or MCP tenant arguments.
public sealed record GitHubPullRequestScope(long RepositoryId,string[] Actions);
public sealed record GitHubPullRequestInput(long RepositoryId,long PullRequestId,int Number,string Action,bool Draft,bool? Merged);
public static class GitHubPullRequest {
    public static void ValidateScope(GitHubPullRequestScope scope) {
        if(scope.RepositoryId<=0||scope.Actions is null||scope.Actions.Length is 0 or >32||scope.Actions.Distinct(StringComparer.Ordinal).Count()!=scope.Actions.Length||scope.Actions.Any(x=>string.IsNullOrEmpty(x)||x.Length>64||x.Any(c=>c!='_'&&(c<'a'||c>'z'))))throw new ArgumentException("GITHUB_SCOPE_INVALID");
    }
    // Call ONLY after authenticating raw bytes. This validates shape/scope, not provenance.
    // Headers are not covered by GitHub's body HMAC: GUID dedup is not an anti-replay timestamp.
    public static GitHubPullRequestInput ValidateVerified(JsonElement body,string eventType,string deliveryId,GitHubPullRequestScope scope) {
        ValidateScope(scope);
        if(eventType!="pull_request")throw new InvalidOperationException("SOURCE_SCOPE_DENIED");
        if(!Guid.TryParseExact(deliveryId,"D",out _))throw new InvalidOperationException("GITHUB_INPUT_INVALID");
        try {
            Unique(body,0);
            var repository=body.GetProperty("repository");var pr=body.GetProperty("pull_request");
            long repositoryId=repository.GetProperty("id").GetInt64();
            long prId=pr.GetProperty("id").GetInt64();int number=body.GetProperty("number").GetInt32();
            var action=body.GetProperty("action").GetString();
            if(repositoryId<=0||prId<=0||number<=0||pr.GetProperty("number").GetInt32()!=number||action is null)throw new InvalidOperationException("GITHUB_INPUT_INVALID");
            bool draft=pr.GetProperty("draft").GetBoolean();
            var mergedValue=pr.GetProperty("merged");
            bool? merged=mergedValue.ValueKind==JsonValueKind.Null?null:mergedValue.GetBoolean();
            if(repositoryId!=scope.RepositoryId||!scope.Actions.Contains(action,StringComparer.Ordinal))throw new InvalidOperationException("SOURCE_SCOPE_DENIED");
            return new(repositoryId,prId,number,action,draft,merged);
        } catch(Exception e)when(e is KeyNotFoundException or FormatException or OverflowException || e is InvalidOperationException && e.Message is not ("SOURCE_SCOPE_DENIED" or "GITHUB_INPUT_INVALID")) {
            throw new InvalidOperationException("GITHUB_INPUT_INVALID");
        }
    }
    private static void Unique(JsonElement node,int depth) {
        if(depth>32)throw new InvalidOperationException("GITHUB_INPUT_INVALID");
        if(node.ValueKind==JsonValueKind.Object) {
            var names=new HashSet<string>(StringComparer.Ordinal);
            foreach(var p in node.EnumerateObject()) {if(!names.Add(p.Name))throw new InvalidOperationException("GITHUB_INPUT_INVALID");Unique(p.Value,depth+1);}
        } else if(node.ValueKind==JsonValueKind.Array)foreach(var x in node.EnumerateArray())Unique(x,depth+1);
    }
}
