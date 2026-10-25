# Evidence-backed fix: use current sensitive environment API

The published Wasmer7.5 schema explicitly deprecates getAppSecrets/getAppSecret/upsertAppSecrets/deleteAppSecret in favor of DeployApp.envVars and updateEnvVars. This explains why the old CLI secret path is not the appropriate current integration; a production null response is not silently interpreted as empty.

Source: https://github.com/wasmerio/wasmer/blob/v7.5.0/lib/backend-api/schema.graphql . EnvVarUpdate supports name/value/sensitive and delete-by-name; sensitive=true hides the value from GraphQL. The driver now uses the supported API with existing WASMER_TOKEN, TLS verification and no redirects. No token scope changes or new credentials are needed. Values are supplied only in approved mutation bodies, never logs, files, package config, or command arguments. Queries request names and sensitivity flags, never values.

Browser verification establishes owner r33drichards, app webhook-mcp-router, canonical ID da_K6AIot5U1ND7 and empty accessible environment editor. Driver verifies the owner/name lookup returns that exact ID and a complete filtered metadata connection before mutation. It refuses an existing approved name, unknown identity, null/incomplete connection or non-sensitive write. Writes/deletes address only the three approved names. Cleanup uses the same current API; unrelated environment variables are preserved. Redeploy uses the published redeployActiveAppVersion operation.

Five offline tests pass: exact deletion scope, no writes without state, null-metadata fail-closed, rejection of unrelated/non-sensitive mutations, and sensitive API transfer with no secret values logged or persisted. Actual modern API execution and hosted E2E still require browser dispatch of the manual test workflow. Its new metadata preflight runs before any deployment writes, so failures stop safely.

---

# Edge secret preflight result

Read-only inspection run40162443039 completed with exit1: `error: app not found`. No secret values were requested. No write was attempted by that workflow.

The exact string comes from Wasmer7.5.0 backend-api `get_app_secrets`, which converts a null `getAppSecrets` GraphQL response to this error. App identifier resolution has different contextual errors. The earlier deployment successfully resolved r33drichards/webhook-mcp-router and obtained https://webhook-mcp-router.wasmer.app before the secret preflight. Thus the evidence establishes a null secret-list response, not that the app necessarily disappeared or that the list is empty.

Sources: https://github.com/wasmerio/wasmer/blob/v7.5.0/lib/backend-api/src/query.rs and https://github.com/wasmerio/wasmer/blob/v7.5.0/lib/cli/src/commands/app/secrets/utils/mod.rs . No documented matching fix was found in the bounded source/issue search. Do not treat null as empty, skip verification, copy secrets into app.yaml, expand token permissions, or blindly rerun deployment.

Required browser coordination: inspect the dedicated app in the existing authorized Wasmer account, confirm current owner/name/app ID and whether Settings → Environment Vars/secret management is accessible and lists any of the three POC names. Do not reveal values or change grants. This distinguishes an identifier/backend issue from an account-permission issue. The three GitHub environment secrets remain pending cleanup for the approved test session; maximum cleanup deadline October26 04:25 UTC. The existing account token is unchanged.

Remaining resources: the dedicated app, its published package and two synthetic volumes were created by run40162019712. No Wasmer service-secret creation call or hosted E2E occurred. This worker has no browser tool; current publication is not blocked, but there is no evidence-backed code fix yet.
