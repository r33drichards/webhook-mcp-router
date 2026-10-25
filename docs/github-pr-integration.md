# Superseded trial scope

The latest first slice is generic all-event ingress from mcp-js, not PR-only. See [generic-webhook-first-slice.md](generic-webhook-first-slice.md). The opt-in PR validator below remains available but must NOT be enabled for that trial. Jev is identified as TypeSafe and deferred to a follow-up; earlier unresolved-provider questions below are historical.

# GitHub PR milestone (issue #1)

This milestone uses the existing Railway Keycloak in a separate webhook-router realm. Keep its current4GB allocation and existing realm/client behavior; no restart/resize or live changes are made by this code. dip means the MCP application client, not Azure management IAM. Jev's exact technology/version remains unconfirmed; no language substitution or new evaluator is implemented.

## Existing behavior reused

Raw-body SHA256 HMAC precedes JSON/policy evaluation. Trusted operator source mapping selects tenant; request bodies cannot select a tenant. SQL receipt/outbox transaction deduplicates TenantId+Source+DeliveryId and rejects a conflicting body hash. Dispatch is at-least-once with leases/retries; exactly-once callback receipt is not promised. Request logs are separate rows per attempt, bounded, tenant-scoped and redacted; unverified payloads are omitted. OPA has bounded input/output/deadline, no policy-network builtins and only registered subscription IDs as results. No arbitrary callback URL is accepted from a policy.

## New opt-in adapter

Add optional PascalCase GitHubPullRequest to a tenant's operator settings, containing RepositoryId (positive immutable GitHub repository ID) and Actions (explicit nonempty string array). There is no default repository/action selection. Omitted field preserves the generic POC mode; real PR registration must use the scoped adapter.

The adapter runs after signature validation and before registry reads/evaluation. It requires event pull_request, GUID delivery ID, positive repository/PR IDs and consistent positive PR numbers; validates draft boolean and nullable merged boolean, rejects duplicate JSON keys and wrong field types, and enforces the repository/action allowlist. It is a validated subset, not a complete GitHub schema. Unknown additional properties remain untrusted data. Actions/repository selections in tests are synthetic only.

Existing Rego input stays `{provider:"github",type:"pull_request",body:<verified JSON>}`. The typed adapter is not a new policy language. Existing strict route result schema is retained, including duplicate/extra property rejection. Typed policy-language authoring, validate/preview/activate workflow and Jev execution remain future work pending the technology decision.

Runtime now supplies configured SourceId to receipts and generated event IDs, instead of constant github. SourceId is an operator-owned bounded identifier. This changes event IDs/receipt namespace relative to the undeployed POC: no live rollout has occurred, but any future migration of existing receipts needs explicit handling. The current config permits one source per tenant; multiple sources per tenant would require a separately reviewed configuration model.

## Operational limits and remaining decisions

- Which owner/repository (and verified immutable ID), or exact list of repositories?
- Which pull_request actions: e.g. opened/reopened/synchronize/closed, and is merged-only filtering intended? These are examples, not selected defaults. Reviews, review comments and issue comments are distinct event types, not implicitly included.
- Repository webhook or GitHub App installation? A single repository hook is the smaller integration, but no choice/permission is assumed.
- Which internal tenant/source and approved endpoint/callback/subscription destination? No actual values or credentials are committed.
- Exact dip product/repository/version and token acquisition/refresh/Authorization-header support? Its own Keycloak service client needs router:read plus requests:read for exploration; subscriptions:write only if intended.
- What is “type safe Jev”: exact package/project URL, version, syntax and sample desired filter, additional evaluator or replacement?

GitHub's signature authenticates body bytes, not delivery/event headers. GUID validation plus durable dedup prevents same-ID duplicate work; it does not provide a timestamp replay window or prevent reuse of a valid body with a changed delivery ID. Do not invent provider timestamps. Any stronger replay/freshness rule needs an explicit accepted tradeoff.

The POC accepts at most64KiB, while GitHub can send much larger webhook bodies; oversize returns413 and logs metadata without payload. Raising that limit is not part of this change. PR-mode ping is currently rejected as out-of-scope; add a separately tested signed ping acknowledgement before real registration rather than treating it as a PR. Logs redact all strings, including action/title/body, so examples preserve structure/numbers/booleans but are explicitly incomplete and may not support text-filter authoring. Do not relax redaction silently.

## Integration sequence

1. Resolve repository/actions/installation choice and Jev/dip identities.
2. Configure healthy isolated Keycloak realm/client through the assigned infrastructure owner, preserving4GB/no restart.
3. Verify actual issued iss/aud/azp/sub/scope and tenant mapping; configure only approved ingress/callback keys.
4. Complete schema, managed identity, exact network and package activation gates. Existing1922c593 package does not contain this new adapter; rebuild a newly approved revision before deploying it.
5. Run synthetic scoped PR ingress through persisted policy/outbox and controlled signed callback, plus same-ID/concurrent/conflicting-body and cross-tenant denials. Add signed ping handling and HTTP-level scoped-adapter tests before live registration.
6. Only then configure the specifically approved real webhook and dip connector. Keep delivery scheduling, retention jobs and actual hosted E2E distinct from infrastructure readiness.

Schema subset checked against https://github.com/octokit/webhooks/blob/main/payload-schemas/api.github.com/common/pull-request.schema.json (merged is nullable).

Sources: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries and https://docs.github.com/en/webhooks/webhook-events-and-payloads . Issue: https://github.com/r33drichards/webhook-mcp-router/issues/1 . No real webhook, credential, grant or remote configuration was created by this work.
