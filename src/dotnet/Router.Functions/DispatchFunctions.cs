using System.Text.Json;
using Azure.Identity;
using Azure.Storage.Queues;
using Microsoft.Azure.Functions.Worker;
using Router.Core;
namespace Router.Functions;
public sealed class DispatchSignal {
    public static bool Enabled=>Environment.GetEnvironmentVariable("ROUTER_DISPATCH_ENABLED")=="true";
    public async Task SendAsync(DispatchWakeup wakeup,TimeSpan delay,CancellationToken ct) {
        if(!Enabled)return;
        DestinationManagement.Id(wakeup.TenantId);DestinationManagement.Id(wakeup.SourceId);
        string account=Environment.GetEnvironmentVariable("AzureWebJobsStorage__accountName")??"";
        if(account.Length is <3 or >24||account.Any(c=>!char.IsAsciiLetterLower(c)&&!char.IsAsciiDigit(c)))throw new InvalidOperationException("DISPATCH_STORAGE_INVALID");
        var queue=new QueueClient(new Uri($"https://{account}.queue.core.windows.net/router-dispatch"),new ManagedIdentityCredential(),new QueueClientOptions{MessageEncoding=QueueMessageEncoding.Base64});
        // Queue is explicitly provisioned by the operator; no CreateIfNotExists here.
        await queue.SendMessageAsync(JsonSerializer.Serialize(wakeup),delay,TimeSpan.FromDays(2),ct);
    }
}
public sealed class DispatchFunctions(IRouterRuntime runtime) {
    [Function("RouterDispatch")]
    public Task Dispatch([QueueTrigger("router-dispatch",Connection="RouterQueue")]string message,CancellationToken ct) {
        if(message.Length>512)throw new InvalidOperationException("DISPATCH_MESSAGE_INVALID");
        using var document=JsonDocument.Parse(message,new JsonDocumentOptions{MaxDepth=3});
        if(document.RootElement.ValueKind!=JsonValueKind.Object||document.RootElement.EnumerateObject().Count()!=2||document.RootElement.EnumerateObject().Select(p=>p.Name).Distinct(StringComparer.Ordinal).Count()!=2)throw new InvalidOperationException("DISPATCH_MESSAGE_INVALID");
        var wakeup=JsonSerializer.Deserialize<DispatchWakeup>(message)??throw new InvalidOperationException("DISPATCH_MESSAGE_INVALID");
        DestinationManagement.Id(wakeup.TenantId);DestinationManagement.Id(wakeup.SourceId);
        return runtime.DispatchAsync(wakeup,ct);
    }
    // Low-frequency crash recovery avoids keeping free SQL awake via frequent polling.
    [Function("RouterReconcile")]
    public Task Reconcile([TimerTrigger("0 17 3 * * *",RunOnStartup=false,UseMonitor=true)]TimerInfo timer,CancellationToken ct)=>runtime.ReconcileAsync(ct);
}
