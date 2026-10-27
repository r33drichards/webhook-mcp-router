using System.Text.Json;
using System.Text.Json.Nodes;
using Router.Core;
namespace Router.Mcp;

// Fixed public protocol metadata. Never compose a challenge from request input,
// policy text, JWT claims, tenant IDs or exception messages.
public static class PolicyOAuth {
    public const string Metadata = "https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/.well-known/oauth-protected-resource/api/mcp";
    public static string[]? Scopes(string? name) => name switch {
        "policies_get" => ["router:read","policies:read"],
        "policies_validate" => ["router:read","policies:test"],
        "policies_preview" => ["router:read","policies:test","destinations:read"],
        "policies_apply" => ["router:read","policies:write"],
        _ => null
    };
    public static JsonObject? RequireScopes(TenantContext tenant,string? name) {
        var scopes=Scopes(name);if(scopes is null)return null;
        try {foreach(var scope in scopes)tenant.Demand(scope);return null;}
        catch(UnauthorizedAccessException) {
            string challenge="Bearer resource_metadata=\""+Metadata+"\", error=\"insufficient_scope\", error_description=\"Authorize the required policy scopes\", scope=\""+string.Join(' ',scopes)+"\"";
            return new JsonObject {
                ["isError"]=true,
                ["content"]=new JsonArray(new JsonObject{["type"]="text",["text"]="Required policy scopes are unavailable. Authorization cannot change your tenant or operator-granted permissions."}),
                ["_meta"]=new JsonObject{["mcp/www_authenticate"]=new JsonArray(challenge)}
            };
        }
    }
    public static void Annotate(JsonObject tool) {
        var scopes=Scopes(tool["name"]?.GetValue<string>());if(scopes is null)return;
        tool["_meta"]=new JsonObject{["securitySchemes"]=new JsonArray(new JsonObject{["type"]="oauth2",["scopes"]=JsonSerializer.SerializeToNode(scopes)})};
    }
    // SDK 2.3.0 Tool retains _meta but has no top-level securitySchemes member.
    // Add the documented ChatGPT field at the existing SDK outgoing JSON hook;
    // do not replace SDK transport or deserialize an unknown field and lose it.
    public static void MirrorSchemes(JsonObject result) {
        if(result["tools"] is not JsonArray tools)return;
        foreach(var tool in tools.OfType<JsonObject>())
            if(Scopes(tool["name"]?.GetValue<string>()) is not null && tool["_meta"] is JsonObject meta && meta["securitySchemes"] is JsonArray schemes)
                tool["securitySchemes"]=schemes.DeepClone();
    }
}
