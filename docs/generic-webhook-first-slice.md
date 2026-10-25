# Generic webhook first slice ([issue #1](https://github.com/r33drichards/webhook-mcp-router/issues/1))

Latest scope supersedes PR-only intake and new NixOS Keycloak deployment assumptions. Use existing Railway Keycloak, isolated webhook-router realm,4GB unchanged/no restart. dip is a scoped MCP application connector, not Azure IAM. Jev/TypeSafe belongs to a [follow-up issue #2](https://github.com/r33drichards/webhook-mcp-router/issues/2) and is NOT required, installed, called, or activated by this slice.

## Trial contract

Receive all available repository webhook event types from r33drichards/mcp-js only. GitHub repository ID961207108 was verified using the authorized GitHub connector. Operator source ID mcp-js-github maps to a trusted tenant. Set optional GitHubRepositoryId=961207108 and omit GitHubPullRequest so ingestion is not PR-only. All event names may enter; signature/shape/source checks still apply. Tenant selection never comes from the request.

Default forwarding is deny. First OPA rule: provider github, original repository id961207108/name r33drichards/mcp-js, event pull_request, action labeled, newly added label.name exactly review. Existing labels containing review, other label capitalization, other actions/events/repositories do not match. policies/trial/mcp-js-review.rego selects IDs from tenant-owned destination metadata with tag review; it contains no destination URL. This tag is a proposed trial metadata convention, not an existing registration.

policies/trial/config.proposed.json is explicitly non-activated, has no destinations, no tenant mapping and no credentials. Missing destinations do not block development and result in no forwarding. Actual destination registration is separate authorization.

## Implemented code vs remaining runtime integration

- Existing HMAC verification remains before JSON use; raw body is bounded64KiB. GitHubSource validates repository ID and delivery GUID for every event type. Header event/delivery values are not authenticated by GitHub's body HMAC; no timestamp freshness claim is made.
- Existing logged ingestion preserves raw-byte verification, redacts all strings, omits unverified/malformed bodies, bounds retention/size and scopes reads by authenticated tenant. It logs every attributable attempt separately from receipt dedup. Some uncommon event header names are currently omitted by the log's conservative enum rather than stored unvalidated.
- Existing SQL receipts deduplicate tenant+configured source+delivery ID; conflicting hashes fail and concurrent identical requests accept once. No exactly-once downstream guarantee. SourceId now propagates to receipts/event identities, replacing fixed github; this is a predeployment change, not a live receipt migration.
- PolicyPipeline is a PURE PREVIEW engine: deterministic unique order and stage IDs, original/payload separation, stage data, bounded results/deadlines, fail-closed errors/denials, and registered tenant destination-ID validation. It performs no network or outbox writes. Optional transformations are composable, not a mandatory first-slice stage.
- OpaRouteStage uses the real bounded official OPA process. Input is schema_version, trusted context, original, payload, enrichments (empty for first slice), and destinations [{id,name,tags}]. No URL, auth reference, token or another tenant's metadata appears in that input. OPA returns destination_id+payload; router validates selected IDs and limits. Existing MCP subscription_id evaluator stays separate.
- SqlDestinationReader queries only enabled tenant metadata and demands destinations:read. destination-schema.sql is an explicit optional migration, not applied automatically or live. It has IDs/names/tags/enablement and no URL/auth fields. SQL permissions for this new table are not silently added to already-provisioned identities.
- Generic pipeline activation, metadata registration tools, protected destination URL/auth storage, generic outbox dispatch and retry scheduling are NOT wired into the live HTTP/MCP path yet. Existing ingestion still uses the legacy MCP subscription routing path. Do not claim this preview adds generic delivery automatically or deploy trial settings alone as completion.

## Next implementation boundary

Add a tenant-bound destination registration service with stable ID, bounded name/tags and separately protected target configuration. Management operations need explicit destinations:write; policy and Jev inputs can read metadata only. Keep protected endpoint/auth resolution inside dispatcher; never pass credentials into evaluator arguments or logs. Name/tag fields must not contain credentials. Store registration versions and the approved delivery decision so changed/disabled destinations cannot silently redirect a queued delivery.

Persist generic deliveries separately from MCP event-envelope deliveries, with transactional receipt/outbox records and bounded attempts. Resolve destination ID under the same tenant again at send time. For each approved HTTPS URL enforce no embedded credentials/fragments, approved ports, no redirects, public-address DNS checks including IPv4/IPv6 and rebinding protection that pins the connection to validated addresses while preserving TLS hostname validation. Reject loopback/private/link-local/metadata/reserved ranges. No generic sender is implemented until these checks and a controlled test sink pass.

Set explicit maximum destinations/body/attempts and independent signature credentials per configured delivery target; never reuse GitHub ingress secrets by default. Generic webhook payload is the chosen/transformed event data, not automatically an MCP Events envelope. Document signature header/protocol with the receiving destination before activation. Callback failures remain in durable queue, and receiving systems deduplicate delivery IDs.

## Validation and prerequisites

Local tests exercise generic all-event source validation, unrelated repo/event/label denial, newly-added label matching, typed malformed input, source-ID propagation, invalid-signature-before-parse, logged rejections, default deny, tenant metadata selection, ordered stages, synthetic enrichment consumed by real OPA, optional transformation and timeout/error denial. The synthetic enrichment fixture is not Jev and makes no external call. SQL CI covers metadata tenant scope and receipt concurrency/hash conflicts separately.

Remaining live prerequisites: healthy isolated Keycloak realm/client mapping, dip token/transport capability confirmation, approved SQL connectivity and migration/grants, a newly built application revision (the1922c593 ZIP predates this work), generic dispatcher integration/security tests, exact destination registration/credentials, then hosted synthetic E2E. No actual GitHub hook, external callback, model inference, secret, grant or remote configuration is created here. Root owns issue #1 and all live changes.

## Deferred Jev research

Verified provider is TypeSafe System One POST https://api.typesafe.ai/v1/systemone, pinned model jev-1.14.0. Request state+named typed questions; response model+answers+usage. Noul is probability, not boolean; choice/score carry distributions and confidence. Later integrate validated enrichments.jev and evaluation provenance, with explicit mandatory-gate versus enrichment-only behavior. Jev send must never bypass downstream OPA/destination authorization. No IRC history semantics are imported. Actual HTTP integration, provider-key use, data-sharing approval and costs remain outside first slice.

Primary sources: https://docs.typesafe.ai/api/system-one , https://docs.typesafe.ai/models , https://docs.typesafe.ai/confidence , https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries , https://docs.github.com/en/webhooks/webhook-events-and-payloads .
