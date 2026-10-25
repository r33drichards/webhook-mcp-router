# Actual Functions-host validation

The prior npm installer log records GET https://cdn.functions.azure.com/public/4.0.281211/Azure.Functions.Cli.linux-x64.4.12.0.zip through the environment proxy, returning403. It does not retain response headers/body that would distinguish vendor403 from proxy policy403. This was not an automatic approval-review denial. No alternate local route was used.

The authorized Windows CI lane now uses the documented official npm Core Tools4.12.0 installer and Azurite3.35.0, all runner-local. It boots the built Functions app on127.0.0.1:7071 and checks the new route rejects missing bearer credentials, malformed/unconfigured auth fails closed, and unconfigured ingress fails closed. It then exercises initialize/tools/list/tools/call against the actual host-owned MCP readiness extension. That legacy route is not the new bearer route, and Core Tools normally disables Functions-key authorization locally. These distinctions are asserted/documented rather than claimed as full authentication coverage.

No Azure login, external webhook, billing/resource change or service credential is used. Azurite uses its standard local emulator configuration. Host processes are terminated after the test. This job does not deploy.

Still outstanding after the basic host probe: a configured synthetic HTTPS issuer/JWKS and SQL fixture for successful bearer-route exploration and signed ingress through the real host. The existing direct-handler tests prove application behavior but not the host integration of that successful path. No pass is claimed until the CI probe completes.

Sources: https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local and https://learn.microsoft.com/en-us/azure/azure-functions/functions-core-tools-reference .
