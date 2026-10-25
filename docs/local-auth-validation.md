# Local validation checkpoint

2026-10-25. No Azure/Keycloak configuration, credentials or deployment performed.

Toolchain: installed official .NET SDK 10.0.402; direct compiler at .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll. Standard CLI and direct MSBuild restore fail on the NuGet-Migrations named mutex in this filesystem environment. Direct compilation uses the installed net10 reference assemblies and official NuGet assemblies retrieved from api.nuget.org, without changing home, permissions or using a denied download route.

Commands executed:

```
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-core.rsp
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-auth.rsp
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-storage.rsp
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-mcp.rsp
.tools/dotnet/dotnet /tmp/Router.Checks.dll /workspace/webhook-mcp-router/.tools/opa /workspace/webhook-mcp-router/policies/capabilities.json
.tools/dotnet/dotnet /tmp/Router.AuthChecks.dll
.tools/dotnet/dotnet /tmp/Router.McpChecks.dll
```

Core/Auth/Storage/Mcp direct compilation passed. Auth and Storage direct compilation have CS1701 net8-to-net10 reference-unification warnings; this is not a warning-free project build. Test programs were likewise compiled directly with their project sources and reference assemblies. OPA checks 13/13, OAuth checks 13/13, SDK checks 5/5 passed. SDK tests instantiate a fresh real official MCP server per call, but do not start a Functions host. SQL requires Windows LocalDB CI and was not run locally. New Functions HTTP handlers have not yet compiled or run through a live host.

Publication: dc909893 added approved OAuth/storage/log work. CI40185258405 found invalid nvarchar(4096); b4ddd56f corrected it. CI40185382439 passed tenant policy/subscription/receipt checks before finding READPAST under pooled serializable isolation. f58107ad resets claim isolation; run40185734550 is the verification run, pending at this checkpoint.

A separate tree containing Router.Mcp, new Functions HTTP routes, SDK tests and integration documentation was denied by automatic approval review as beyond the approved publication scope. It did not execute. These files remain local; no alternate publication route was attempted. The narrower SQL fix was independently accepted and published. Endpoint publication needs clarification before retrying the denied action.

Request log hardening local follow-up removes non-allowlisted property names as well as string values, avoiding credentials hidden in arbitrary JSON property names. This deliberately preserves only a sanitized structural example, never a promised full original. It remains local pending the next reviewed publication.

## Terminal CI and direct HTTP handler results

Published head f58107adcce43c0a8bf496b929ac4569c49cc63e: https://github.com/r33drichards/webhook-mcp-router/actions/runs/40185734550 completed SUCCESS, job121146005362. OPA13, OAuth13, SQL/log22 assertions passed. Published Functions project built with zero warnings/errors. SQL tests exercised real Windows LocalDB, tenant policy and subscription boundaries, separate receipt namespaces, outbox lease denial, payload redaction, malformed/oversized handling, cross-tenant log access, pagination/row limits and expiry filtering. This CI does not include unpublished endpoint code.

The new HTTP handler and runtime composition compiled locally via direct Roslyn invocation. Fifteen Router.HttpChecks tests passed (exit0): missing bearer, wrong audience, missing route scope, Origin rejection, unsupported GET, authenticated official-SDK initialize, tenant A/B dispatch, arbitrary tenant argument rejection, bounded MCP body, malformed JSON, custom subscribe with a signed synthetic callback challenge, cross-tenant unsubscribe denial, owning-tenant unsubscribe and no recursive log capture. These invoke HttpEndpoints with DefaultHttpContext and synthetic runtime/store/callback fixtures. They do NOT start the Azure Functions host or contact Keycloak, SQL, Azure or an external callback.

Commands:

```
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-functions.rsp
.tools/dotnet/dotnet exec .tools/dotnet/sdk/10.0.402/Roslyn/bincore/csc.dll @/tmp/router-httpchecks.rsp
.tools/dotnet/dotnet /tmp/Router.HttpChecks.dll
```

No func executable is installed. The recorded Core Tools4.12.0 download403 at https://cdn.functions.azure.com/public/4.0.281211/Azure.Functions.Cli.linux-x64.4.12.0.zip remains the exact local host prerequisite blocker. No retry through another download route was attempted. Ordinary restore still fails with NuGet-Migrations mutex MSB4018, whereas direct compiler tests use public NuGet assemblies successfully retrieved from api.nuget.org.

Endpoint publication remains pending explicit scope clarification after the denied tree action; no retry or alternative route was attempted. Remaining validation: actual Functions-host routing/worker metadata, real HTTPS JWKS rotation/caching behavior, full project build of new endpoint dependencies, SQL-backed signed-ingress-to-callback lifecycle, scheduled retention/outbox processing, and deployment authorization. The in-process passing tests do not establish those outcomes.

## Publication authorization update

The user explicitly approved publication of all remaining project changes. The earlier endpoint-publication gate is superseded by that approval. This authorizes repository publication and CI, not live deployment, credentials or billing changes. The historical denial records above remain accurate for those attempts.
