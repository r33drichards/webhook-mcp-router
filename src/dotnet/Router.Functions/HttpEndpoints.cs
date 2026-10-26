using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.Functions.Worker;
using Router.Core;
namespace Router.Functions;
public sealed class HttpEndpoints(IRouterRuntime runtime) {
    [Function("RouterOAuthMetadata")]
    public IActionResult Metadata([HttpTrigger(AuthorizationLevel.Anonymous,"get",Route=McpDiscovery.Route)] HttpRequest request) {
        request.HttpContext.Response.Headers.CacheControl="public, max-age=300";
        return new JsonResult(McpDiscovery.Document()){ContentType="application/json",StatusCode=200};
    }
    private static UnauthorizedResult Challenge(HttpRequest request) {
        request.HttpContext.Response.Headers.WWWAuthenticate=McpDiscovery.Challenge;
        return new UnauthorizedResult();
    }
    [Function("RouterMcpHttp")]
    public async Task<IActionResult> Mcp([HttpTrigger(AuthorizationLevel.Anonymous,"post","get","delete",Route="api/mcp")] HttpRequest request,CancellationToken ct) {
        // Anonymous disables the Functions key requirement here, NOT application authorization.
        // Every verb, notification and method passes bearer validation before SDK dispatch.
        if(request.Headers.ContainsKey("Origin"))return new StatusCodeResult(403);
        TenantContext tenant;
        try {
            if(request.Headers.Authorization.Count!=1||!request.Headers.Authorization.ToString().StartsWith("Bearer ",StringComparison.OrdinalIgnoreCase))return Challenge(request);
            tenant=await runtime.Validator.ValidateAsync(request.Headers.Authorization.ToString()[7..],"router:read",ct);
        } catch(UnauthorizedAccessException e){return e.Message=="SCOPE_DENIED"?new StatusCodeResult(403):Challenge(request);}
        catch(OperationCanceledException)when(ct.IsCancellationRequested){throw;}
        catch{return new StatusCodeResult(503);}
        if(request.Method!="POST")return new StatusCodeResult(405);
        if(request.ContentType?.Split(';')[0].Trim().Equals("application/json",StringComparison.OrdinalIgnoreCase)!=true)return new StatusCodeResult(415);
        string accept=request.Headers.Accept.ToString();if(!accept.Contains("application/json",StringComparison.OrdinalIgnoreCase)||!accept.Contains("text/event-stream",StringComparison.OrdinalIgnoreCase))return new StatusCodeResult(406);
        if(request.Headers.TryGetValue("MCP-Protocol-Version",out var version)&&version!="2025-06-18")return new BadRequestResult();
        try {
            byte[] body=await Read(request.Body,ct);
            using var output=new MemoryStream();
            bool wrote=await runtime.Mcp(tenant).ProcessAsync(body,output,ct);
            if(output.Length>1048576)return new StatusCodeResult(500);
            return wrote?new FileContentResult(output.ToArray(),"text/event-stream"):new StatusCodeResult(202);
        }catch(ArgumentException){return new StatusCodeResult(413);}
        catch(System.Text.Json.JsonException){return new BadRequestResult();}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested){return new StatusCodeResult(504);}
        catch(OperationCanceledException){throw;}
        catch{return new StatusCodeResult(500);}
    }
    [Function("RouterWebhook")]
    public async Task<IActionResult> Webhook([HttpTrigger(AuthorizationLevel.Anonymous,"post",Route="api/webhooks/{source}")] HttpRequest request,string source,CancellationToken ct) {
        try {
            var ingress=runtime.Ingress(source);if(ingress is null)return new NotFoundResult();
            byte[] body=await Read(request.Body,ct,true);
            bool accepted=await ingress.AcceptAsync(request.Headers["X-GitHub-Delivery"].ToString(),request.Headers["X-GitHub-Event"].ToString(),body,request.Headers["X-Hub-Signature-256"].ToString(),ct);
            return new OkObjectResult(new{accepted});
        }catch(ArgumentException){return new StatusCodeResult(413);}
        catch(InvalidOperationException e)when(e.Message=="INGRESS_LIMIT"){return new StatusCodeResult(413);}
        catch(InvalidOperationException e)when(e.Message=="SIGNATURE_INVALID"){return new UnauthorizedResult();}
        catch(InvalidOperationException e)when(e.Message=="SOURCE_SCOPE_DENIED"){return new StatusCodeResult(403);}
        catch(InvalidOperationException e)when(e.Message=="GITHUB_INPUT_INVALID"){return new BadRequestResult();}
        catch(System.Text.Json.JsonException){return new BadRequestResult();}
        catch(OperationCanceledException){throw;}
        catch{return new StatusCodeResult(503);}
    }
    private static async Task<byte[]> Read(Stream stream,CancellationToken ct,bool captureOversize=false) {
        using var output=new MemoryStream();byte[] buffer=new byte[4096];int n;
        while((n=await stream.ReadAsync(buffer,ct))>0){if(output.Length+n>65536){if(captureOversize){await output.WriteAsync(buffer.AsMemory(0,65537-(int)output.Length),ct);return output.ToArray();}throw new ArgumentException("BODY_LIMIT");}await output.WriteAsync(buffer.AsMemory(0,n),ct);}
        return output.ToArray();
    }
}
