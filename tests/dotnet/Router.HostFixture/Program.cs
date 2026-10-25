using System.Text.Json;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Router.Auth;
using Router.Core;
using Router.Functions;
using Router.Mcp;
using Router.Storage;

// Test-only executable. It links unchanged production HTTP handlers, validates actual JWTs,
// and uses real LocalDB stores. Static synthetic public keys replace network JWKS retrieval.
var builder=FunctionsApplication.CreateBuilder(args);builder.ConfigureFunctionsWebApplication();
builder.Services.AddSingleton<IRouterRuntime>(_=>new FixtureRuntime());builder.Build().Run();
sealed record Config(string Connection,string PublicJwks,string IngressKey,string Opa,string Capabilities);
sealed class FixtureRuntime:IRouterRuntime,IDisposable {
    private readonly Config config=JsonSerializer.Deserialize<Config>(Environment.GetEnvironmentVariable("ROUTER_HOST_FIXTURE")??"")!;
    private readonly HttpClient http=new(new DenyNetwork());
    private TokenValidator? validator;
    public TokenValidator Validator=>validator??=new TokenValidator("https://synthetic-issuer.example.invalid","router",
        [new("a","svc-a","tenant-a",["router:read","requests:read","subscriptions:write"]),new("b","svc-b","tenant-b",["router:read","requests:read","subscriptions:write"])],new Keys(new JsonWebKeySet(config.PublicJwks).GetSigningKeys().ToArray()));
    public RequestServer Mcp(TenantContext tenant)=>new(tenant,new RequestExplorer(tenant,new SqlRequestLog(config.Connection,tenant,new())),new EventService(new SqlRegistrationWriter(config.Connection,tenant),"https://callback.example.invalid",Convert.FromBase64String(config.IngressKey),http));
    public LoggedIngress? Ingress(string source) {
        if(source!="source-a")return null;
        var tenant=new TenantContext("tenant-a","source-a",["requests:append"]);var key=Convert.FromBase64String(config.IngressKey);
        return new(new Ingestion(new SqlRegistrationReader(config.Connection,tenant),new SqlOutbox(config.Connection,tenant),new OpaEvaluator(config.Opa,config.Capabilities),tenant,key),new SqlRequestLog(config.Connection,tenant,new()),new RequestCapture(),key);
    }
    public async Task DispatchAsync(DispatchWakeup wakeup,CancellationToken ct) {
        if(wakeup.TenantId!="tenant-a"||wakeup.SourceId!="source-a")throw new UnauthorizedAccessException("FIXTURE_SOURCE_DENIED");
        await using var db=new Microsoft.Data.SqlClient.SqlConnection(config.Connection);await db.OpenAsync(ct);
        await using var cmd=new Microsoft.Data.SqlClient.SqlCommand("INSERT dbo.FixtureWakeup(Received) VALUES(1)",db);await cmd.ExecuteNonQueryAsync(ct);
    }
    public void Dispose()=>http.Dispose();
    private sealed class Keys(IReadOnlyList<SecurityKey> keys):ISigningKeys {public Task<IReadOnlyList<SecurityKey>> GetAsync(bool refresh,CancellationToken ct)=>Task.FromResult(keys);}
    private sealed class DenyNetwork:HttpMessageHandler {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken ct)=>throw new InvalidOperationException("FIXTURE_OUTBOUND_DISABLED");}
}
