namespace Router.Functions;

// Public deployment metadata, never derived from Host/Forwarded headers, JWTs or
// tenant configuration. This does not change the token validator's audience.
public static class McpDiscovery {
    public const string Resource = "https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/api/mcp";
    public const string Issuer = "https://keycloak-production-295b.up.railway.app/realms/webhook-router";
    public const string Route = ".well-known/oauth-protected-resource/api/mcp";
    public const string Metadata = "https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/" + Route;
    public const string Challenge = "Bearer resource_metadata=\"" + Metadata + "\", scope=\"router:read\"";
    public static object Document() => new {
        resource = Resource,
        authorization_servers = new[] { Issuer },
        scopes_supported = new[] { "router:read", "requests:read", "destinations:read" },
        bearer_methods_supported = new[] { "header" }
    };
}
