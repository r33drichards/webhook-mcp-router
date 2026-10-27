using System.Text.Json;
using Router.Auth;
using Router.Core;
using Router.Mcp;
using Router.Storage;
namespace Router.Functions;

// Operator configuration only; never populated from request data. No default credentials.
public sealed class RouterRuntime:IRouterRuntime,IDisposable {
    private readonly object sync=new();private TokenValidator? validator;private HttpsSigningKeys? keys;
    private TenantSettings[]? settings;
    private readonly SafeWebhookTransport deliveryHttp=new();
    private readonly DispatchSignal dispatchSignal=new();
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
                if(t.GenericRouting&&(t.GitHubRepositoryId is null||t.GitHubPullRequest is not null))throw new InvalidOperationException("GENERIC_SOURCE_CONFIG_INVALID");
                if(t.GitHubRepositoryId is <=0)throw new InvalidOperationException("SOURCE_CONFIG_INVALID");
                if(t.GitHubPullRequest is not null)Router.Core.GitHubPullRequest.ValidateScope(t.GitHubPullRequest);
                if(!t.GenericRouting) {
                    if(!Uri.TryCreate(t.Callback,UriKind.Absolute,out var url)||url.Scheme!="https"||url.UserInfo.Length!=0||url.Query.Length!=0||url.Fragment.Length!=0||url.IsLoopback||System.Net.IPAddress.TryParse(url.Host,out _))throw new InvalidOperationException("CALLBACK_CONFIG_INVALID");
                    if(Convert.FromBase64String(t.CallbackKeyBase64??"").Length is <24 or >64)throw new InvalidOperationException("KEY_CONFIG_INVALID");
                }
                if(Convert.FromBase64String(t.IngressKeyBase64).Length is <24 or >64)throw new InvalidOperationException("KEY_CONFIG_INVALID");

            }
            if(auth.Clients.Any(g=>!tenants.Any(t=>t.TenantId==g.TenantId)))throw new InvalidOperationException("MAPPING_INVALID");
            var signing=new HttpsSigningKeys(new Uri(auth.Jwks));
            try {validator=new TokenValidator(auth.Issuer,auth.Audience,auth.Clients,signing);keys=signing;settings=tenants;}catch{signing.Dispose();throw;}
        }
    }
    public RequestServer Mcp(TenantContext tenant) {
        Ensure();var config=settings!.Single(t=>t.TenantId==tenant.TenantId);
        var log=new SqlRequestLog(config.LogReadConnection,tenant,new());
        var events=config.GenericRouting?null:new EventService(new SqlRegistrationWriter(config.RegistryWriteConnection,tenant),config.Callback,Convert.FromBase64String(config.CallbackKeyBase64),callbackHttp);
        var management=new DestinationManagement(tenant,new SqlDestinationStore(config.RegistryWriteConnection,tenant),config.DestinationBindings??[]);
        var policyManagement=config.GenericRouting?new PolicyManagement(tenant,new SqlPolicyStore(config.RegistryWriteConnection,tenant),new SqlDestinationReader(config.RegistryReadConnection,tenant),new OpaEvaluator(Environment.GetEnvironmentVariable("OPA_EXECUTABLE")??"",Environment.GetEnvironmentVariable("OPA_CAPABILITIES")??""),config.SourceId):null;
        return new(tenant,new RequestExplorer(tenant,log),events,management,policyManagement);
    }
    public LoggedIngress? Ingress(string source) {
        Ensure();var config=settings!.SingleOrDefault(t=>t.SourceId==source);if(config is null)return null;
        var tenant=new TenantContext(config.TenantId,"ingress:"+config.SourceId,["requests:append","destinations:read"]);
        var key=Convert.FromBase64String(config.IngressKeyBase64);
        var evaluator=new OpaEvaluator(Environment.GetEnvironmentVariable("OPA_EXECUTABLE")??"",Environment.GetEnvironmentVariable("OPA_CAPABILITIES")??"");
        IIngressProcessor processor=config.GenericRouting
            ?new GenericIngestion(new SqlRegistrationReader(config.RegistryReadConnection,tenant),new SqlDestinationReader(config.RegistryReadConnection,tenant),new SqlOutbox(config.OutboxConnection,tenant,genericWebhook:true),evaluator,tenant,key,config.SourceId,config.GitHubRepositoryId!.Value,c=>dispatchSignal.SendAsync(new(config.TenantId,config.SourceId),TimeSpan.Zero,c))
            :new Ingestion(new SqlRegistrationReader(config.RegistryReadConnection,tenant),new SqlOutbox(config.OutboxConnection,tenant),evaluator,tenant,key,config.GitHubPullRequest,config.SourceId,config.GitHubRepositoryId);
        return new(processor,new SqlRequestLog(config.LogWriteConnection,tenant,new()),new RequestCapture(),key);
    }
    public async Task DispatchAsync(DispatchWakeup wakeup,CancellationToken ct) {
        if(!DispatchSignal.Enabled)return;Ensure();
        var config=settings!.SingleOrDefault(t=>t.TenantId==wakeup.TenantId&&t.SourceId==wakeup.SourceId&&t.GenericRouting)??throw new InvalidOperationException("DISPATCH_SOURCE_DENIED");
        var tenant=new TenantContext(config.TenantId,"dispatcher",["destinations:deliver"]);
        var processor=new GenericDeliveryProcessor(new SqlDestinationResolver(config.OutboxConnection,tenant),new EnvironmentDeliverySecrets(tenant),new SqlOutbox(config.OutboxConnection,tenant,genericWebhook:true),tenant,deliveryHttp);
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(25));
        bool worked=false;for(int i=0;i<2;i++){if(!await processor.OnceAsync(deadline.Token))break;worked=true;}
        if(worked)await dispatchSignal.SendAsync(wakeup,TimeSpan.FromSeconds(30),ct);
    }
    public async Task ReconcileAsync(CancellationToken ct) {
        if(!DispatchSignal.Enabled)return;Ensure();
        foreach(var tenant in settings!.Where(t=>t.GenericRouting))await dispatchSignal.SendAsync(new(tenant.TenantId,tenant.SourceId),TimeSpan.Zero,ct);
    }
    public void Dispose(){keys?.Dispose();callbackHttp.Dispose();deliveryHttp.Dispose();}
}
