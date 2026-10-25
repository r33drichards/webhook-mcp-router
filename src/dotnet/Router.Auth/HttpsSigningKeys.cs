using Microsoft.IdentityModel.Tokens;
namespace Router.Auth;

// One instance per configured issuer. Fixed JWKS URL, no token-controlled URLs or redirects.
public sealed class HttpsSigningKeys : ISigningKeys,IDisposable {
    private readonly Uri endpoint;
    private readonly HttpClient http;
    private readonly SemaphoreSlim gate=new(1,1);
    private IReadOnlyList<SecurityKey> cached=Array.Empty<SecurityKey>();
    private DateTimeOffset updated=DateTimeOffset.MinValue,attempted=DateTimeOffset.MinValue;
    public HttpsSigningKeys(Uri endpoint) {
        if(endpoint.Scheme!="https"||endpoint.UserInfo.Length!=0||endpoint.Fragment.Length!=0||endpoint.Query.Length!=0)throw new ArgumentException("JWKS_CONFIG_INVALID");
        this.endpoint=endpoint;
        http=new HttpClient(new SocketsHttpHandler {AllowAutoRedirect=false,UseProxy=false,ConnectTimeout=TimeSpan.FromSeconds(3)}) {Timeout=TimeSpan.FromSeconds(5)};
    }
    public async Task<IReadOnlyList<SecurityKey>> GetAsync(bool refresh,CancellationToken ct) {
        await gate.WaitAsync(ct);
        try {
            var now=DateTimeOffset.UtcNow;
            if(cached.Count>0 && now-updated<TimeSpan.FromMinutes(5) && !refresh)return cached;
            // Prevent invalid kid floods from becoming a JWKS request flood. Fail closed when expired.
            if(now-attempted<TimeSpan.FromSeconds(30)) {
                if(cached.Count>0&&now-updated<TimeSpan.FromMinutes(5))return cached;
                throw new UnauthorizedAccessException("SIGNING_KEYS_UNAVAILABLE");
            }
            attempted=now;
            using var response=await http.GetAsync(endpoint,HttpCompletionOption.ResponseHeadersRead,ct);
            if(!response.IsSuccessStatusCode||response.Content.Headers.ContentLength>65536)throw new UnauthorizedAccessException("SIGNING_KEYS_UNAVAILABLE");
            using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(5));
            await using var stream=await response.Content.ReadAsStreamAsync(deadline.Token);
            using var output=new MemoryStream();byte[] buffer=new byte[4096];int n;
            while((n=await stream.ReadAsync(buffer,deadline.Token))>0) {if(output.Length+n>65536)throw new UnauthorizedAccessException("SIGNING_KEYS_UNAVAILABLE");await output.WriteAsync(buffer.AsMemory(0,n),deadline.Token);}
            var jwks=new JsonWebKeySet(System.Text.Encoding.UTF8.GetString(output.ToArray()));
            if(jwks.Keys.Count is 0 or >32)throw new UnauthorizedAccessException("SIGNING_KEYS_UNAVAILABLE");
            var allowed=jwks.Keys.Where(k=>k.Kty=="RSA"&&(k.Use is null or "sig")&&(k.Alg is null or "RS256")&&k.D is null&&!string.IsNullOrEmpty(k.Kid)).Cast<SecurityKey>().ToArray();
            if(allowed.Length==0||allowed.Select(k=>k.KeyId).Distinct(StringComparer.Ordinal).Count()!=allowed.Length)throw new UnauthorizedAccessException("SIGNING_KEYS_UNAVAILABLE");
            cached=allowed;updated=now;return cached;
        } finally {gate.Release();}
    }
    public void Dispose(){http.Dispose();gate.Dispose();}
}
