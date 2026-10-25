using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Router.Core;

public sealed class EventProtocolException(int code, string message) : Exception(message) { public int Code { get; }=code; }

// Domain adapter for the inspected draft events/* wire contract. Hosting the
// same methods on the Functions MCP endpoint requires a separate tested hook.
public sealed class EventService(IRegistrationWriter writer, string callback, byte[] key, HttpClient http)
{
    public const string EventName="webhook.received";
    public async Task<JsonObject> InvokeAsync(TenantContext tenant,string method,JsonElement parameters,CancellationToken ct=default) {
        tenant.Demand(method=="events/list"?"router:read":"subscriptions:write");
        string owner=tenant.TenantId;
        try {
            if(method=="events/list") {
                Fields(parameters,"cursor","_meta");
                if(parameters.TryGetProperty("cursor",out var cursor)&&cursor.ValueKind!=JsonValueKind.Null)throw Invalid();
                return JsonNode.Parse("""{"events":[{"name":"webhook.received","description":"Verified routed webhook","delivery":["webhook"],"inputSchema":{"type":"object","properties":{},"additionalProperties":false},"payloadSchema":{"type":"object"}}]}""")!.AsObject();
            }
            if(method is not ("events/subscribe" or "events/unsubscribe"))throw new EventProtocolException(-32601,"Method not found");
            bool subscribe=method=="events/subscribe";
            Fields(parameters,subscribe?["name","arguments","delivery","ttlMs","cursor","_meta"]:["name","arguments","delivery","_meta"]);
            var args=parameters.GetProperty("arguments");var delivery=parameters.GetProperty("delivery");
            Fields(delivery,subscribe?["mode","url","secret"]:["mode","url"]);
            if(parameters.GetProperty("name").GetString()!=EventName || args.ValueKind!=JsonValueKind.Object || args.EnumerateObject().Any() || delivery.GetProperty("mode").GetString()!="webhook" || delivery.GetProperty("url").GetString()!=callback)throw Invalid();
            if(!Uri.TryCreate(callback,UriKind.Absolute,out var uri)||uri.Scheme!="https"||uri.UserInfo!=""||uri.Fragment!=""||uri.Query!=""||key.Length is <24 or >64)throw Invalid();
            string identity=JsonSerializer.Serialize(new object[]{owner,callback,EventName,new Dictionary<string,string>()});
            string id="sub_"+Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
            if(!subscribe) { await writer.DeleteSubscriptionAsync(owner,id,ct);return new JsonObject(); }
            string secret=delivery.GetProperty("secret").GetString()??"";
            if(!secret.StartsWith("whsec_",StringComparison.Ordinal))throw Invalid();
            byte[] provided=Convert.FromBase64String(secret[6..]);
            if(Convert.ToBase64String(provided)!=secret[6..] || !CryptographicOperations.FixedTimeEquals(provided,key))throw Invalid();
            long ttl=3600000;
            if(parameters.TryGetProperty("ttlMs",out var t)) { if(!t.TryGetInt64(out ttl)||ttl<=0)throw Invalid(); }
            ttl=Math.Min(ttl,86400000);
            if(parameters.TryGetProperty("cursor",out var c)&&c.ValueKind!=JsonValueKind.Null&&c.GetString()!=id+":0")throw Invalid();
            await VerifyCallbackAsync(id,ct);
            var expires=DateTimeOffset.UtcNow.AddMilliseconds(ttl);
            await writer.SaveSubscriptionAsync(new(id,owner,EventName,"{}",callback,Fingerprint(key),expires),ct);
            return new JsonObject { ["id"]=id,["refreshBefore"]=expires.ToString("O"),["cursor"]=id+":0",["truncated"]=false };
        } catch(EventProtocolException) { throw; }
        catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
        catch(JsonException){throw Invalid();}catch(KeyNotFoundException){throw Invalid();}catch(FormatException){throw Invalid();}
        catch(InvalidOperationException){throw Invalid();}
        catch { throw new EventProtocolException(-32603,"Event request failed"); }
    }
    private async Task VerifyCallbackAsync(string id,CancellationToken ct) {
        string challenge=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(32));
        string body=JsonSerializer.Serialize(new {type="verification",challenge});
        string eventId="verify_"+Guid.NewGuid().ToString("N");
        using var bounded=CancellationTokenSource.CreateLinkedTokenSource(ct);bounded.CancelAfter(TimeSpan.FromSeconds(10));
        using var request=SignedRequest(callback,key,id,eventId,body);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,bounded.Token);
        if(!response.IsSuccessStatusCode)throw new EventProtocolException(-32000,"Callback verification failed");
        await using var stream=await response.Content.ReadAsStreamAsync(bounded.Token);
        byte[] data=new byte[4097];int length=0;
        while(length<data.Length){int n=await stream.ReadAsync(data.AsMemory(length),bounded.Token);if(n==0)break;length+=n;}
        if(length>4096)throw Invalid();
        using var result=JsonDocument.Parse(data.AsMemory(0,length));
        if(result.RootElement.GetProperty("challenge").GetString()!=challenge)throw new EventProtocolException(-32000,"Callback verification failed");
    }
    public static HttpRequestMessage SignedRequest(string url,byte[] key,string subscription,string eventId,string body) {
        string timestamp=DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(System.Globalization.CultureInfo.InvariantCulture);
        string signature=Convert.ToBase64String(HMACSHA256.HashData(key,Encoding.UTF8.GetBytes(eventId+"."+timestamp+"."+body)));
        var r=new HttpRequestMessage(HttpMethod.Post,url){Content=new StringContent(body,Encoding.UTF8,"application/json")};
        r.Headers.Add("webhook-id",eventId);r.Headers.Add("webhook-timestamp",timestamp);r.Headers.Add("webhook-signature","v1,"+signature);r.Headers.Add("X-MCP-Subscription-Id",subscription);return r;
    }
    public static string Fingerprint(byte[] key)=>Convert.ToHexStringLower(SHA256.HashData(key));
    private static EventProtocolException Invalid()=>new(-32602,"Invalid event request parameters");
    private static void Fields(JsonElement value,params string[] allowed) {
        if(value.ValueKind!=JsonValueKind.Object || value.EnumerateObject().Any(p=>!allowed.Contains(p.Name)) || value.ValueKind==JsonValueKind.Object && value.EnumerateObject().Select(p=>p.Name).Distinct(StringComparer.Ordinal).Count()!=value.EnumerateObject().Count())throw Invalid();
    }
}
