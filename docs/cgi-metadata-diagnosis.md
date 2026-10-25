# Hosted panic traced to missing REQUEST_METHOD

Browser runtime logs for requests at 06:41:31 and 07:02:08 UTC on October25 identify cgi-0.6.0/src/lib.rs:259:30, “no entry found for key”. Upstream v0.6.0 line259 is `req = req.method(env_vars["REQUEST_METHOD"].as_str());`:
https://github.com/amandasaurus/rust-cgi/blob/v0.6.0/src/lib.rs#L259

This identifies the immediate cause of the official Rust baseline's 500: REQUEST_METHOD is absent from its CGI environment. It is not a missing secret or an OPA failure. Go1.25.5 net/http/cgi also rejects missing REQUEST_METHOD (child.go lines53–55), which is a plausible common cause of the earlier Go failures, but no matching Go runtime diagnostic has yet established that inference.

The local guest harness supplied REQUEST_METHOD manually, explaining why those checks passed without establishing the hosted metadata contract. A new negative check omits only that key and requires the exact same panic location/message. This check does not deploy or supply credentials.

Artifact audit: deployment-job logs for run40166166069 show the official Rust module SHA256 cfb524895407fd0117a32d9aa6fa536113f068ee29393c851c9de8b930417b90, matching validation. Browser confirms active deployment ro_eGIvt5oIJJxB points to r33drichards/webhook-mcp-router@=0.0.1-ci.245de875c23c.official, with only kind/name/owner/package and no volume mounts. Build-generated manifest selects server, wasi ABI, https://webc.org/runner/wcgi and rfc-3875, matching the official guide. The module exports _start. Wasmer7.5 deploy.rs lines787–803 resolve package . relative to app.yaml, ruling out the suspected working-directory resolution error in this script. CI validates the raw module, however, not the registry-downloaded WEBC bytes or live command selection.

Remaining root-cause boundary: determine why the deployed request reaches CGI code without request metadata. Read-only inspection should verify the active release's actual packaged command runner/entrypoint/atom digest and compare the version-specific URL with the main app URL. If these match WCGI, a credential-free request-metadata probe should emit only presence flags for a fixed CGI-key allowlist, never values or all environment variables. This distinguishes missing request metadata from execution during startup. No new deployment is currently dispatched.

Do not hard-code REQUEST_METHOD=GET in app environment: that would misclassify POST webhooks and MCP calls. Do not purge snapshots without evidence; the mere presence of a purge button does not establish stale state. A correct fix must preserve per-request method, path, body length and headers at the actual runner boundary. The existing no-credential/no-paid-change limits remain.

## Published package and normalized runtime audit

Read-only runs40171992234 and40172167597 confirmed active version dav_neGIvtLuvJx8, package0.0.1-ci.245de875c23c.official, WEBCv3 hash b847c8c8122705a92413c49aacb80ca92fcae7a13976f6f563fcb11dbefc14bf, entrypoint/atom server, runner https://webc.org/runner/wcgi and rfc-3875 dialect. No corruption or generation error was reported. URL and URLs fields expose only https://webhook-mcp-router.wasmer.app; permalink ogh5izczvew3 is an identifier, so no unique URL has been invented.

Normalized App.v1 configuration contains workload source and locality/WASI/web_gateway capabilities, with no explicit command override visible. That shape alone does not prove proxy versus WCGI selection. Environment values were never printed. The packaged runner metadata is correct, leaving runtime invocation/request metadata as the diagnostic boundary.

Prepared workflow **Diagnose hosted CGI request envelope** (cgi-envelope.yml). It builds a small std-only Rust program with the same compiler and WCGI package configuration. It does not parse CGI or default a missing method to GET. It emits only booleans for fixed CGI metadata presence, GET/POST equality, successful bounded stdin read, empty stdin and exact synthetic input match; no arbitrary environment values, headers or body bytes are exposed. It writes the same fixed report to stderr with CGI_ENVELOPE_PROBE marker so logs remain useful if Edge does not interpret its valid CGI stdout response. Local tests include missing REQUEST_METHOD without panic. Hosted GET and POST are both attempted, even if GET fails. Deployment remains manual, isolated and credential-free; no probe has yet been dispatched.

## First envelope result and probe correction

Run40172471704 completed failed at07:25:01UTC: three GETs and three POSTs all returned HTTP500, no JSON report. Requests took roughly15.7seconds before each500. This timing is consistent with, but does not prove, a blocked stdin read in the diagnostic. The first probe read until EOF before printing its marker, so it could obscure startup metadata when no CGI body length is supplied. It did not create credentials.

Corrected probe emits CGI_ENVELOPE_START presence booleans before reading stdin and reads only a valid CONTENT_LENGTH of at most64bytes. Missing/invalid length never triggers a read; it is reported through stdin_read_ok=false. A regression keeps the guest's stdin pipe open with no CGI metadata and requires a reply within10seconds. This is a diagnostic correction, not an application fix or successful hosted result.

## Corrected envelope: effective execution does not match WCGI contract

Run [40172909795](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40172909795), commit 8a2d67d0346fc857336cefc447bf51daa45f95c7, completed failure at 2026-10-25 07:30:22 UTC. Local guest validation passed; hosted GET and POST still returned 500. Parent browser inspection at 07:30:07 and 07:30:13 found REQUEST_METHOD, CONTENT_LENGTH, SERVER_PROTOCOL and GATEWAY_INTERFACE absent; SCRIPT_NAME present; stdin was not read because length was absent. The probe did not panic. Literal CGI stdout status, headers and fixed JSON response appeared in runtime logs instead of reaching the HTTP client.

This is strong evidence of execution outside the expected per-request WCGI adapter, consistent with proxy/raw-command startup. It is not proof of the internal Edge mode-selection bug: startup execution remains a possible explanation. SCRIPT_NAME is supplied by the package annotation, so its presence does not demonstrate request metadata injection.

Primary-source discriminator: [Wasmer logging documentation](https://github.com/wasmerio/docs.wasmer.io/blob/6f160c961ad8db0dcba163ef5a3000a90f953065/content/edge/observability/logging.mdx) says proxy mode captures both output streams, while WCGI consumes stdout for the HTTP response and captures stderr. The published package audit already verified the WCGI runner URI, entrypoint and dialect. This narrows the discrepancy to deployment/runtime selection or startup handling, rather than CGI parser, SDK, OPA or missing service secrets.

[Wasmer 7.5 app configuration source](https://github.com/wasmerio/wasmer/blob/v7.5.0/lib/config/src/app/mod.rs) has no typed app-level runner selector. The GraphQL schema contains WorkloadRunnerV1.wcgi, but the supported publish input accepts user-facing configuration/YAML; its presence alone does not establish a supported app.yaml override. Do not invent an override or write internal configuration.

Smallest next supported diagnostic: retain the exact current credential-free package and app identity, change only documented app.yaml debug:true, and collect one GET and one synthetic POST response plus matching runtime logs. [Official configuration documentation](https://docs.wasmer.io/edge/configuration/) states debug enables detailed gateway error responses. This tests whether the gateway is waiting for a proxy socket or reports another adapter failure, without rebuilding packages, adding credentials, hard-coding a method or purging snapshots. Restore debug:false afterward. No such change has been executed in this checkpoint. If detailed errors still do not identify the mismatch, escalate this minimal reproduction to Wasmer with package runner evidence; no support message has been sent.

No new service secrets were created. Wasmer temporary-secret cleanup remains verified from the preceding credential-bearing run; the three GitHub environment copies remain parent-owned pending removal before the original deadline.

## Debug-mode result and final diagnostic boundary

Temporary documented debug:true with empty app variables did not reveal a deeper error: GET07:38:04UTC still generic500, request7767c82c-2bfe-42b8-a3dd-eb6a5049519e. Original YAML without debug was restored and reload verified; package unchanged. POST was blocked by the executor proxy, not observed on Edge. UI logs covered the restored deployment rather than the debug request, so no proxy-timeout cause is established.

Consolidated reproduction, evidence limits and remaining platform-side read-only question: [wcgi-runner-support-report.md](wcgi-runner-support-report.md). Hosted testing is blocked at runner/request-adapter selection. No further speculative deployment or external support contact performed.
