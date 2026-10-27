# Policy OAuth scope upgrade

The protected-resource document advertises the existing `router:read`,
`requests:read`, `destinations:read` and approved `policies:read`, `policies:test`,
`policies:write`. Advertising a scope is not a grant. Runtime authorization still
intersects the signed token's scopes with the operator's exact client/subject/
tenant binding. Existing read-only tokens cannot activate policies.

The four policy tools declare their own OAuth requirements. Preview also requires
`destinations:read`. A known policy tool called without its required scopes
returns an error with a fixed `mcp/www_authenticate` scope-upgrade challenge,
before evaluation, database access or writes. Unknown arguments and downstream
tenant/database failures do not generate this challenge. Reauthorization cannot
change the tenant binding or operator-granted permissions.

SDK 2.3.0 retains `_meta` but has no top-level `securitySchemes` property. The
existing SDK outgoing JSON hook mirrors only the fixed policy declarations from
`_meta.securitySchemes` to the documented top-level field. SDK wire and actual
Functions-host tests check that declarations and error metadata survive transport.
The server still requires `router:read` at entry; anonymous requests do not gain
access through this metadata.

## Existing ChatGPT connector

Preserve the existing app identity, OAuth client and callback. Inspect its current
plugin configuration without exposing credentials. If its explicit requested
scope list contains only the original three read scopes, update that same list to
include the three approved policy scopes. Publish through the existing app's
update mechanism, then reauthorize. Reconnecting an unchanged explicit three-scope
configuration does not establish policy access. Check only scope names and
operation results, never log tokens. An OAuth refresh may retain the earlier
scope grant; verify the newly issued authorization rather than assuming success.

## Verification and limits

Verify catalog declarations, `policies_get`, candidate `policies_validate` and
`policies_preview`, and denied cross-tenant access. Do not activate or overwrite a
live user policy as a smoke test. Get and preview require runtime SQL connectivity;
validation alone does not prove SQL access. This correction does not open SQL,
change IAM, create credentials, enable dispatch or add destination permissions.

References:
- https://developers.openai.com/plugins/build/auth
- https://github.com/modelcontextprotocol/csharp-sdk/blob/v2.3.0/src/ModelContextProtocol.Core/Protocol/Tool.cs
