# Webhook MCP Router

Experimental runtime investigation for a single Go webhook receiver, embedded OPA evaluator, and official Go MCP SDK control plane. Proposed public repository: `r33drichards/webhook-mcp-router`.

**Not deployment-ready.** The combined Go service is uncompiled because dependency downloads were blocked locally. A synthetic authenticated CGI/tool/callback fixture is now implemented in `spike/hosted`, but its SDK integration is uncompiled and its Wasmer/hosted behavior untested. Exact event subscriptions and Edge durability remain incomplete. No hosted MCP end-to-end pass is claimed.

Locally verified: compiled OPA policy execution through a Wasmer C host (fallback approach), a standard-library Go CGI guest preserving synthetic request data, and mapped-file persistence across local instances. Standard Go WASI networking failed host connectivity tests. CGI guest success is not a WCGI HTTP-host test.

- [Requirements](webhook-router-requirements.md)
- [Exact runtime evidence and blockers](docs/runtime-evidence.md)
- [CI bootstrap and deployment gates](docs/ci-bootstrap.md)
- [Storage options](docs/storage-options.md)

`spike/ingress/source` contains the pinned upstream webhook source and a local experimental patch; upstream license is retained. `src/router.py` is an earlier, unvalidated prototype, not the selected architecture. Nix build definitions are preliminary and have not run. CI is prepared locally; publication and GitHub execution status must be recorded separately.
