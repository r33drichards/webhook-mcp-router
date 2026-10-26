# Real GitHub OIDC qualification — pending publication/run approval

## Live checkpoint supplied by supervising operator

Keycloak26.8.1 deployment `0bd348d1-3be5-4b24-968f-48edb51579e5` succeeded. Existing mcp realm retained (migration/import skipped), same H2 volume and4GB allocation; realm discovery/JWKS returned200 with two keys. Interactive browser login remains untested. Deployment source: railway-browser-mcp branch `keycloak-upgrade-26-8-1-20261026`, commit `6583ef940435896c00be815517bd5aab36b0061a`; main and unrelated services unchanged. This is operator-provided verification, not a second live inspection by this task.

Upgrade is complete and no longer a prerequisite. No webhook-router realm or federation/bootstrap has been created. Prior admin-creation denial remains subject to normal review with materially relevant new approval/context; no bypass is authorized. Next proposed write is isolated realm creation, followed by explicitly scoped clients/trust; no existing mcp realm changes.


## Exact proposed branch and trust

Publish only the reviewed workflow and harness to branch `ci/keycloak-real-oidc-qualification` in `r33drichards/webhook-mcp-router`. Its scoped push trigger will run immediately after publication; publication approval must therefore include this test run. A later workflow_dispatch is available only once GitHub recognizes the workflow on its default branch; do not merge merely to enable dispatch. No pull_request trigger, new environment, repository OIDC settings change or live trust.

- Issuer: `https://token.actions.githubusercontent.com`.
- Subject: `repo:r33drichards@57335981/webhook-mcp-router@1432792940:ref:refs/heads/ci/keycloak-real-oidc-qualification`.
- Audience: `https://localhost:18444/realms/webhook-router` (disposable runner realm only).
- Context must also match repository_id1432792940, repository_owner_id57335981, exact repository and ref. Owner/repository IDs verified through GitHub metadata. Current GitHub documentation says new repositories use immutable-ID subjects; runtime must confirm this exact subject. Fail on mismatch; do not auto-learn a subject or change repo settings.
- Temporary Keycloak federated-jwt client uses exact subject/issuer, signature verification and assertion reuse disabled. Discover issuer/JWKS over certificate-validated HTTPS, allow only the GitHub token hostname for JWKS.

This is **test trust**, destroyed with the runner fixture. Production audience, protected-environment subject, trust bootstrap and provider state are separate.

## Permission and resource diff

New `.github/workflows/keycloak-real-oidc.yml`: workflow permissions empty; the single test job gets only contents:read and id-token:write. ubuntu-24.04 standard hosted runner, timeout20minutes, concurrency1 without cancellation. Checkout pinned11d5960a326750d5838078e36cf38b85af677262 and credentials not persisted. No repository secrets, Azure/Wasmer/Railway login, artifacts or external resource provisioning. No larger/paid runner selection.

One disposable Keycloak26.8.1 container, digest a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b, max4GB/2CPU. Private Docker network has outbound access for real JWKS; it is not a no-egress network. No published Docker ports; host test tunnel binds loopback only. New generated fixture credentials/H2 data stay under RUNNER_TEMP and are deleted. Terraform1.15.8 archive SHA256 d25ce7b6902013ad905db3d2eab0be4cd905887fe88b81a6171b8d5503c31f3d verified against official release checksum listing. Provider5.10.0 uses existing reviewed lockfile, readonly init.

## Tests

Reuse the qualified39-assertion harness structure, replacing synthetic signing/static public key with actual GitHub issuance and Keycloak HTTPS JWKS validation. Positive exchange, replay rejection, a genuinely issued wrong-audience token, wrong trusted issuer/subject against genuine tokens, tampered signature, bounded wait for real expiration, short-lived Keycloak token, realm-local administration and denial of browser/master/new-realm access. Provider validate/apply/no-drift/destroy disabled synthetic client, fresh federation per operation. Wrong issuer/subject tests deliberately change disposable trust; they do not claim ability to obtain GitHub-signed tokens with arbitrary claims. No claim of real GitHub key rotation coverage.

Assertions/tokens never printed or saved; provider output discarded. Logs include fixed assertion names only. Python finally and workflow always cleanup remove container/network/data/state/keys; ephemeral runner disposal is the last fallback if hard termination prevents cleanup. Maximum expiry wait650seconds; fail if longer. Timeout/failed cleanup is reported, not success.

## Validation performed

Python compilation, YAML permission/timeout checks, TLS/JWKS/replay configuration checks and execution of wrong-context guard passed locally. This workflow has NOT run; no actual GitHub issuance result claimed. Local public discovery GET failed proxy CONNECT403; no alternate access attempted. The intended GitHub runner execution is a separately reviewed supported environment, not a local denial bypass.

## Live upgrade coordination

Parent reports separate user authorization for live upgrade despite absence of verified backup, accepting data/configuration loss, downtime and browser-login risk. Assigned native operator is sole live writer. Preserve existing volume and4GB; no intentional wipe. Verified backup is not a gating condition under that decision. No production-copy rehearsal is required. Synthetic tests do not create a recovery guarantee; without a restorable database, restoring an image alone cannot guarantee rollback after schema migration. Existing IaC covers proposed router resources, not every historical browser realm/user/session/key. Do not claim IaC restores data it never recorded.

## Sources

- https://docs.github.com/actions/reference/openid-connect-reference
- https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/
- https://github.com/actions/checkout/blob/11d5960a326750d5838078e36cf38b85af677262/action.yml
- https://releases.hashicorp.com/terraform/1.15.8/terraform_1.15.8_SHA256SUMS
