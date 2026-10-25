using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;

namespace Router.Functions;

public sealed class Tools
{
    [Function("RouterStatus")]
    public object Status([McpToolTrigger("router_status", "Report implementation readiness; does not access credentials or event data")] ToolInvocationContext context)
        => new { ready = false, policyEvaluator = "official-opa-process", persistence = "sql-outbox-not-implemented", eventExtension = "pending-port" };
}
