# Webhook MCP Router

**Current direction:** C# isolated Azure Functions on classic Windows Consumption, Azure SQL, and allowance alerts. [Plan and current evidence](docs/csharp-consumption-plan.md). Windows CI passed the bounded official OPA subprocess tests and built the MCP Functions project. Azure deployment, SQL/outbox integration and custom event-method support remain pending; the current MCP scaffold exposes only readiness status. Billing/provisioning are paused pending explicit account and budget decisions.

The runtime investigation below describes the historical Go/Wasmer phase.

Experimental runtime investigation for a single Go webhook receiver, embedded OPA evaluator, and official Go MCP SDK control plane. Public repository: `r33drichards/webhook-mcp-router`.

**Not deployment-ready.** GitHub CI has passed the official SDK fixture's native tests, WASI build, and actual Wasmer CGI initialize/tools/create/fresh-instance readback. This uses manually supplied CGI metadata and mapped local storage, not hosted WCGI or Edge persistence. Exact event-subscription lifecycle and hosted outbound callbacks remain incomplete/unverified. The combined Go/OPA service passed native tests and WASI compilation; embedded Go OPA evaluation also passed under Wasmer (match/nonmatch/malformed-input assertions). Deployment stays gated.

Locally verified: compiled OPA policy execution through a Wasmer C host (fallback approach), a standard-library Go CGI guest preserving synthetic request data, and mapped-file persistence across local instances. Standard Go WASI networking failed host connectivity tests. CGI guest success is not a WCGI HTTP-host test.

- [Requirements](webhook-router-requirements.md)
- [Exact runtime evidence and blockers](docs/runtime-evidence.md)
- [CI bootstrap and deployment gates](docs/ci-bootstrap.md)
- [Storage options](docs/storage-options.md)

`spike/ingress/source` contains the pinned upstream webhook source and a local experimental patch; upstream license is retained. `src/router.py` is an earlier, unvalidated prototype, not the selected architecture. Nix build definitions are preliminary and have not run. CI is prepared locally; publication and GitHub execution status must be recorded separately.
