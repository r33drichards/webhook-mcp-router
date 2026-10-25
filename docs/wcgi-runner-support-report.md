# Hosted WCGI runner-boundary reproduction

Status as of 2026-10-25 07:38 UTC: **blocked, not fixed**. No hosted MCP initialize, subscription lifecycle or callback-delivery pass is claimed.

## Minimal reproduction

App: `r33drichards/webhook-mcp-router`, public endpoint `https://webhook-mcp-router.wasmer.app`. Current package: `r33drichards/webhook-mcp-router@=0.0.1-ci.8a2d67d0346f.envelope`. No service credentials or volume mounts are required by this probe.

Source and workflow are pinned by [commit 8a2d67d](https://github.com/r33drichards/webhook-mcp-router/tree/8a2d67d0346fc857336cefc447bf51daa45f95c7): `spike/cgi-envelope/main.rs`, `ci/envelope-guest-check.py`, `ci/envelope-hosted-check.py`, `.github/workflows/cgi-envelope.yml`.

The Rust 1.85.0 wasm32-wasip1 program emits a startup marker before reading input, reads only a declared CONTENT_LENGTH bounded to 64 bytes, and emits a valid CGI response containing fixed metadata-presence booleans. It neither defaults REQUEST_METHOD nor parses arbitrary environment values into output. The package command selects `https://webc.org/runner/wcgi`, dialect `rfc-3875`, module/entrypoint `server`. SCRIPT_NAME is supplied by a package annotation, not inferred from a request.

[Run 40172909795](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40172909795) passed local guest GET, POST, missing-method and open-stdin regressions. Hosted three GET and three synthetic POST requests all returned HTTP500; run completed failure at 07:30:22 UTC. Local guest checks explicitly supply CGI metadata and do not establish an Edge adapter pass.

Browser runtime logs at 07:30:07/13 UTC show:

```text
request_method_present=false
content_length_present=false
script_name_present=true
server_protocol_present=false
gateway_interface_present=false
method_is_get=false
method_is_post=false
stdin_read_ok=false
stdin_empty=true
stdin_synthetic=false
```

The literal CGI stdout `Status: 200 OK`, content headers and JSON body also appear in runtime logs. There is no observed process-exit error in those entries. The client still receives500. Missing length prevents a body read by design; this does not prove stdin has no bytes.

## Independent official baseline

The unmodified official Rust template at `wasmerio/wcgi-rust-template` commit `ec51018faf125703b45b5f960b02b45887985e19` also failed on Edge. Logs identify cgi0.6.0 `src/lib.rs:259:30`, which indexes REQUEST_METHOD. A local negative regression reproduces that exact panic by omitting only the key. The baseline's published WEBC was independently audited in read-only runs [40171992234](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40171992234) and [40172167597](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40172167597): correct WCGI runner, entrypoint, dialect, no corruption or generation errors. WEBCv3 SHA256: `b847c8c8122705a92413c49aacb80ca92fcae7a13976f6f563fcb11dbefc14bf`.

## Documented debug test

After verifying empty app variables, browser operator temporarily enabled documented `debug: true` without changing the envelope package. GET at 07:38:04 UTC still returned the generic500 page; request ID `7767c82c-2bfe-42b8-a3dd-eb6a5049519e`. The exact original YAML without debug was restored and save/reload verified. POST was not performed in this stage because the available executor's outbound proxy denied access. That denial is distinct from Edge's hosted500.

Available logs after restoration repeated the missing metadata and CGI stdout. The UI exposed the restored deployment interval 07:38:21–26, not the earlier debug request. Therefore this test did not establish a proxy timeout or provide a deeper gateway cause. Debug is no longer enabled.

## Interpretation and outstanding platform question

[Wasmer's logging documentation](https://github.com/wasmerio/docs.wasmer.io/blob/6f160c961ad8db0dcba163ef5a3000a90f953065/content/edge/observability/logging.mdx) distinguishes proxy mode, which captures stdout and stderr, from WCGI mode, which uses stdout for the HTTP response. Observed behavior is consistent with execution outside the per-request WCGI adapter, possibly raw/proxy startup. Correct package metadata does not prove which runner Edge actually selected. Neither a platform defect nor snapshot involvement is proven.

**Question for platform diagnosis:** why does this package's WCGI command execute without REQUEST_METHOD/CONTENT_LENGTH and have CGI stdout captured as logs instead of returned as HTTP? Is the process a startup invocation or the selected request handler, and what effective runner did the deployment select?

The remaining decisive read-only check is platform-side effective runner/workload selection and gateway trace correlated to the above request ID (and the 07:30 probe interval). Public package metadata and the exposed normalized app config have already been audited; they do not expose enough to answer that question. [Wasmer7.5 app config](https://github.com/wasmerio/wasmer/blob/v7.5.0/lib/config/src/app/mod.rs) offers no typed app-level runner override. An internal GraphQL WCGI input type alone is not justification for inventing YAML fields or mutating internal configuration.

No further speculative deployments, hard-coded request methods, snapshot purges or service-secret recreation are proposed. This report is ready for a user-authorized support inquiry; no support message or external issue has been sent. Existing app/package history remains. Temporary GitHub environment-secret cleanup remains separately pending with the parent operator; no secret values are included here.
