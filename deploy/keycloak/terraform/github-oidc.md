# GitHub Actions OIDC to Keycloak 26.4.7 — proposal only

Yes in principle, but it still ends in Keycloak AdminAPI calls authorized by a short-lived Keycloak token. A GitHub OIDC JWT is not itself a Keycloak administrative access token, and an Azure-audience token must not be reused.

## What exists in this exact version

Keycloak 26.4.7 source contains `federated-jwt` client authentication and an OIDC identity provider implementing client-assertion validation. It is gated by preview feature `client-auth-federated`, not assumed enabled on Railway. OIDC signature validation and the identity provider's client-assertion support must both be enabled. No restart or feature change is authorized in this task.

The federated validator requires the configured external issuer, a **single audience equal to the Keycloak realm issuer URL**, and a maximum expiration window of 300 seconds. The authenticator looks up a client by exact `jwt.credential.sub` and its configured issuer/identity-provider alias. Verify jti/replay handling, clock skew, key rotation and GitHub token lifetime using synthetic/local qualification before live use; do not relax validation for a mismatch.

Sources pinned to 26.4.7:
- [Feature classification](https://github.com/keycloak/keycloak/blob/26.4.7/common/src/main/java/org/keycloak/common/Profile.java)
- [Federated client lookup](https://github.com/keycloak/keycloak/blob/26.4.7/services/src/main/java/org/keycloak/authentication/authenticators/client/FederatedJWTClientAuthenticator.java)
- [OIDC assertion verification](https://github.com/keycloak/keycloak/blob/26.4.7/services/src/main/java/org/keycloak/broker/oidc/OIDCIdentityProvider.java)
- [Issuer/audience/lifetime validator](https://github.com/keycloak/keycloak/blob/26.4.7/services/src/main/java/org/keycloak/authentication/authenticators/client/FederatedJWTClientValidator.java)

Do not conflate this with JWT Authorization Grant: that separate grant arrived as preview in 26.5 and became supported in 26.6. The default private-key JWT client authenticator expects issuer equal to subject, unlike a GitHub-issued JWT; pointing its JWKS setting at GitHub is not an equivalent supported workaround. Standard internal token exchange is not blanket external GitHub-token trust.

## Proposed trust binding (not configured)

- External issuer: `https://token.actions.githubusercontent.com`; obtain its JWKS via validated discovery over HTTPS, no attacker-selected key URL.
- Audience requested from GitHub: exactly `https://<approved-keycloak-origin>/realms/webhook-router` with the actual canonical host substituted; not the Azure resource audience and not the AdminAPI URL.
- Subject: exactly `repo:r33drichards/webhook-mcp-router:environment:keycloak-router-admin` for a separately approved protected GitHub environment. Restrict that environment to main and approved reviewers, with no untrusted pull-request execution or broad wildcard subject. Environment subjects do not themselves encode the branch; protection rules are necessary.
- Stronger workflow binding: separately approve a GitHub custom subject template including immutable repository identity and `job_workflow_ref`, then configure Keycloak with the exact resulting subject. Do not claim26.4's basic matcher automatically evaluates arbitrary GitHub claims or that a name-based default subject prevents repository-name reuse.
- Client: confidential service account `terraform-webhook-router` in the NEW realm, authenticator `federated-jwt`, exact issuer alias and federated subject; only reviewed realm-local management permissions. Application `dip-webhook-router` is a different client and must not receive administration roles.
- Actions: only the approved job receives `id-token: write` and `contents: read`; pinned trusted actions, no fork/PR-controlled code. This configuration is not added to any runnable workflow here.

Intended flow: request GitHub OIDC assertion with the dedicated audience → Keycloak client_credentials token request using JWT client_assertion → restricted Keycloak service-account access token → provider KEYCLOAK_ACCESS_TOKEN → AdminAPI under webhook-router. Token requests and results must never be printed or persisted in public artifacts. Provider5.10 supports supplied access_token and explicitly skips automatic refresh for it; acquire a fresh token per bounded Terraform run. The provider also accepts a supplied JWT assertion, but repeated login/refresh may conflict with assertion expiry/replay; do not assume renewal from GitHub is automatic.

## Choices and gates

1. Without feature changes: ordinary restricted client credentials/private-key JWT is the straightforward existing-version route, but requires an independently approved stored credential. A supplied short-lived Keycloak access token works if an approved issuer/bootstrap process obtains it; that alone does not implement GitHub federation.
2. If preview use and any necessary restart are separately approved: qualify 26.4.7 federated client authentication and exact GitHub trust above in an isolated test first. Existing feature state is unknown; no enablement is performed.
3. Future supported federation/grant path: independently assess an approved Keycloak upgrade. No version upgrade, memory change or service restart is part of this design.

Every option still needs initial authority to create the new realm, administrative service account, role grants and (for OIDC) trust. Existing browser AdminAPI access is not implicit authorization to create them. Current live mutation denial remains in effect; Terraform is not a bypass. The exact approval bundle includes realm/client names, realm-local roles, backend access, external runner reachability, GitHub environment/subject trust and—only if chosen—preview feature enablement/restart.

Provider evidence: [access_token selection and no-refresh behavior](https://github.com/keycloak/terraform-provider-keycloak/blob/v5.10.0/keycloak/keycloak_client.go). Version history: [26.5 introduction](https://www.keycloak.org/2026/01/keycloak-2650-released), [26.6 promotion](https://www.keycloak.org/2026/04/keycloak-2660-released).
