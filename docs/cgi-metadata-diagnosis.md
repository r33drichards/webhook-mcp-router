# Hosted panic traced to missing REQUEST_METHOD

Browser runtime logs for requests at 06:41:31 and 07:02:08 UTC on October25 identify cgi-0.6.0/src/lib.rs:259:30, “no entry found for key”. Upstream v0.6.0 line259 is `req = req.method(env_vars["REQUEST_METHOD"].as_str());`:
https://github.com/amandasaurus/rust-cgi/blob/v0.6.0/src/lib.rs#L259

This identifies the immediate cause of the official Rust baseline's 500: REQUEST_METHOD is absent from its CGI environment. It is not a missing secret or an OPA failure. Go1.25.5 net/http/cgi also rejects missing REQUEST_METHOD (child.go lines53–55), which is a plausible common cause of the earlier Go failures, but no matching Go runtime diagnostic has yet established that inference.

The local guest harness supplied REQUEST_METHOD manually, explaining why those checks passed without establishing the hosted metadata contract. A new negative check omits only that key and requires the exact same panic location/message. This check does not deploy or supply credentials.

Artifact audit: deployment-job logs for run40166166069 show the official Rust module SHA256 cfb524895407fd0117a32d9aa6fa536113f068ee29393c851c9de8b930417b90, matching validation. Browser confirms active deployment ro_eGIvt5oIJJxB points to r33drichards/webhook-mcp-router@=0.0.1-ci.245de875c23c.official, with only kind/name/owner/package and no volume mounts. Build-generated manifest selects server, wasi ABI, https://webc.org/runner/wcgi and rfc-3875, matching the official guide. The module exports _start. Wasmer7.5 deploy.rs lines787–803 resolve package . relative to app.yaml, ruling out the suspected working-directory resolution error in this script. CI validates the raw module, however, not the registry-downloaded WEBC bytes or live command selection.

Remaining root-cause boundary: determine why the deployed request reaches CGI code without request metadata. Read-only inspection should verify the active release's actual packaged command runner/entrypoint/atom digest and compare the version-specific URL with the main app URL. If these match WCGI, a credential-free request-metadata probe should emit only presence flags for a fixed CGI-key allowlist, never values or all environment variables. This distinguishes missing request metadata from execution during startup. No new deployment is currently dispatched.

Do not hard-code REQUEST_METHOD=GET in app environment: that would misclassify POST webhooks and MCP calls. Do not purge snapshots without evidence; the mere presence of a purge button does not establish stale state. A correct fix must preserve per-request method, path, body length and headers at the actual runner boundary. The existing no-credential/no-paid-change limits remain.
