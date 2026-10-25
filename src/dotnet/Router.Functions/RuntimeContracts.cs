using Router.Auth;
using Router.Core;
using Router.Mcp;
namespace Router.Functions;
public sealed record AuthSettings(string Issuer,string Audience,string Jwks,ServiceGrant[] Clients);
public sealed record TenantSettings(string TenantId,string SourceId,string Callback,string CallbackKeyBase64,string IngressKeyBase64,string RegistryReadConnection,string RegistryWriteConnection,string OutboxConnection,string LogReadConnection,string LogWriteConnection,GitHubPullRequestScope? GitHubPullRequest=null,long? GitHubRepositoryId=null,bool GenericRouting=false,DestinationBinding[]? DestinationBindings=null);
public interface IRouterRuntime { TokenValidator Validator {get;} RequestServer Mcp(TenantContext tenant); LoggedIngress? Ingress(string source); Task DispatchAsync(DispatchWakeup wakeup,CancellationToken ct)=>Task.CompletedTask; Task ReconcileAsync(CancellationToken ct)=>Task.CompletedTask; }
