# Targeted credential-free startup diagnostic

Run 40163890496 returned HTTP 500 on all 24 initialize attempts, with mostly oversized platform HTML responses. Hosted lifecycle was skipped; Wasmer secret removal, credential-free redeployment and old-bearer rejection were verified at 05:04:40 UTC. Browser logs did not expose errors during the initialization interval. The current unauthenticated error page says Application Error / An unknown error occurred; it does not establish the earlier cause.

The candidate now separates packaged CGI startup from fixture initialization. GET /_poc/health returns only a constant runtime-ready status, without inspecting environment values, opening storage or constructing MCP/OPA handlers. Other methods on that route return 405. Functional routes still load the fixture and enforce existing authentication. Invalid startup configuration emits fixed developer-defined codes to stderr and a 503 JSON response; values and underlying exceptions are never included.

Manual workflow: **Diagnose credential-free packaged CGI startup**, main, confirm_no_spend=true after current free allowance verification. It uses only existing WASMER_TOKEN, refuses to proceed if any approved POC service-secret name exists, tests native code and actual guest responses, and deploys the same isolated app once. It expects hosted health 200, then /mcp 503 with POC_SIGNING_CONFIG_INVALID because signing credentials deliberately remain absent. No POC credentials are restored or created. This is a diagnostic deployment, not MCP or event-delivery success.

Interpretation: failed health isolates the failure before fixture configuration; successful health plus the expected fixed code proves WCGI-to-Go handling, but not functional authenticated configuration. Unexpected codes identify a narrower stage. Any full lifecycle retry still requires reviewing the diagnostic evidence; this workflow does not dispatch one automatically.

Current local validation: Python scripts compile, workflow YAML parses, eight lifecycle tests pass. Native Go and actual Wasmer startup assertions are pending CI, not claimed locally. The local unauthenticated endpoint probe was blocked by proxy CONNECT 403; no bypass or alternative local route was attempted.

## Constant CGI comparison

The credential-free integrated health probe failed on Edge in run40164818062 despite local guest success. Prepared **Compare constant CGI on Edge** (constant-cgi.yml), main, confirm_no_spend=true, deploys a standard-library-only CGI binary using the same pinned WASIX Go compiler, WCGI runner, ABI, certificate filesystem mapping and existing volume configuration. Only application code/dependencies change; package version receives a .constant suffix. It serves the same constant health response and returns 404 POC_DIAGNOSTIC_ONLY for every other request. No functional MCP, webhook or receipt handler exists in this binary.

The workflow records wasmer inspect output (imports and entry exports), validates the module, and asserts both responses in fresh local Wasmer guests before deploying. It refuses existing POC service-secret names and supplies only WASMER_TOKEN. No credentials are created. The companion actual-service CI records both integrated and constant module metadata for comparison. Hosted execution remains pending manual dispatch; this is not a successful Edge result.

The runner URL, wasi ABI and rfc-3875 dialect match the official Rust WCGI tutorial at https://docs.wasmer.io/edge/guides/wcgi-on-edge/ . No official example binary has been executed here; matching manifest fields alone does not prove runtime compatibility. If constant CGI fails too, dependency initializers are not sufficient to explain the failure; package/platform/Go runtime handling remains. Existing volume configuration is deliberately unchanged to keep this comparison focused.

## Stock-Go comparison

The WASIX constant CGI also failed on Edge (run40165387023), so the next isolated variable is the compiler. **Compare stock Go constant CGI on Edge** (stock-cgi.yml) builds the unchanged constant source with official Go1.25.5, matching the upstream version of the tested WASIX fork. The same build flags, package mapping, runner, ABI and volume configuration remain; package version gets .constant-stock solely to distinguish artifacts. Push CI only validates locally. Deployment requires manual workflow_dispatch on main with confirm_no_spend=true and successful validation. Only WASMER_TOKEN is supplied, no POC credentials. Module import output and fresh guest response assertions are captured.

This is a toolchain comparison, not a decision to abandon native OPA or adopt stock Go for networking. If both constant variants fail on Edge, the next priority is reproducing the official WCGI example/configuration rather than adding application components. Stock-Go validation/hosted results are pending until the respective runs complete.
