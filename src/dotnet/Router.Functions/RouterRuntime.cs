using System.Text.Json;
using Router.Auth;
using Router.Core;
using Router.Mcp;
using Router.Storage;
namespace Router.Functions;

// Operator configuration only; never populated from request data. No default credentials.
public sealed record AuthSettings(string Issuer,string Audience,string Jwks,ServiceGrant[] Clients);
public sealed record TenantSettings(string TenantId,string SourceId,string Callback,string CallbackKeyBase64,string IngressKeyBase64,string RegistryReadConnection,string RegistryWriteConnection,string OutboxConnection,string LogReadConnection,string LogWriteConnection,GitHubPullRequestScope? GitHubPullRequest=null);
public interface IRouterRuntime { TokenValidator Validator {get;} RequestServer Mcp(TenantContext tenant); LoggedIngress? Ingress(string source); }
public sealed class RouterRuntime:IRouterRuntime,IDisposable {
    private readonly object sync=new();private TokenValidator? validator;private HttpsSigningKeys? keys;
    private TenantSettings[]? settings;
    private readonly HttpClient callbackHttp=new(new SocketsHttpHandler{AllowAutoRedirect=false,UseProxy=false,ConnectTimeout=TimeSpan.FromSeconds(3)}){Timeout=TimeSpan.FromSeconds(10)};
    public TokenValidator Validator {get {Ensure();return validator!;}}
    private static T Load<T>(string name) {
        var text=Environment.GetEnvironmentVariable(name);
        if(string.IsNullOrWhiteSpace(text))throw new InvalidOperationException("CONFIG_MISSING");
        try {return JsonSerializer.Deserialize<T>(text)??throw new InvalidOperationException("CONFIG_INVALID");}
        catch(JsonException){throw new InvalidOperationException("CONFIG_INVALID");}
    }
    private void Ensure() {
        lock(sync) {
            if(validator is not null)return;
            var auth=Load<AuthSettings>("ROUTER_AUTH_JSON");
            var tenants=Load<TenantSettings[]>("ROUTER_TENANTS_JSON");
            if(tenants.Length is 0 or >100||tenants.Select(t=>t.TenantId).Distinct().Count()!=tenants.Length||tenants.Select(t=>t.SourceId).Distinct().Count()!=tenants.Length)throw new InvalidOperationException("CONFIG_INVALID");
            foreach(var t in tenants) {
                _=new TenantContext(t.TenantId,"configuration",[]);
                if(string.IsNullOrEmpty(t.SourceId)||t.SourceId.Length>64||t.SourceId.Any(c=>!char.IsAsciiLetterOrDigit(c)&&c is not ('_' or '-')))throw new InvalidOperationException("SOURCE_CONFIG_INVALID");
                if(t.GitHubPullRequest is not null)Router.Core.GitHubPullRequest.ValidateScope(t.GitHubPullRequest);
                if(!Uri.TryCreate(t.Callback,UriKind.Absolute,out var url)||url.Scheme!="https"||url.UserInfo.Length!=0||url.Query.Length!=0||url.Fragment.Length!=0||url.IsLoopback||System.Net.IPAddress.TryParse(url.Host,out _))throw new InvalidOperationException("CALLBACK_CONFIG_INVALID");
                if(Convert.FromBase64String(t.CallbackKeyBase64).Length is <24 or >64||Convert.FromBase64String(t.IngressKeyBase64).Length is <24 or >64)throw new InvalidOperationException("KEY_CONFIG_INVALID");
            }
            if(auth.Clients.Any(g=>!tenants.Any(t=>t.TenantId==g.TenantId)))throw new InvalidOperationException("MAPPING_INVALID");
            var signing=new HttpsSigningKeys(new Uri(auth.Jwks));
            try {validator=new TokenValidator(auth.Issuer,auth.Audience,auth.Clients,signing);keys=signing;settings=tenants;}catch{signing.Dispose();throw;}
        }
    }
    public RequestServer Mcp(TenantContext tenant) {
        Ensure();var config=settings!.Single(t=>t.TenantId==tenant.TenantId);
        var log=new SqlRequestLog(config.LogReadConnection,tenant,new());
        return new(tenant,new RequestExplorer(tenant,log),new EventService(new SqlRegistrationWriter(config.RegistryWriteConnection,tenant),config.Callback,Convert.FromBase64String(config.CallbackKeyBase64),callbackHttp));
    }
    public LoggedIngress? Ingress(string source) {
        Ensure();var config=settings!.SingleOrDefault(t=>t.SourceId==source);if(config is null)return null;
        var tenant=new TenantContext(config.TenantId,"ingress:"+config.SourceId,["requests:append"]);
        var key=Convert.FromBase64String(config.IngressKeyBase64);
        var evaluator=new OpaEvaluator(Environment.GetEnvironmentVariable("OPA_EXECUTABLE")??"",Environment.GetEnvironmentVariable("OPA_CAPABILITIES")??"");
        return new(new Ingestion(new SqlRegistrationReader(config.RegistryReadConnection,tenant),new SqlOutbox(config.OutboxConnection,tenant),evaluator,tenant,key,config.GitHubPullRequest,config.SourceId),new SqlRequestLog(config.LogWriteConnection,tenant,new()),new RequestCapture(),key);
    }
    public void Dispose(){keys?.Dispose();callbackHttp.Dispose();}
}
