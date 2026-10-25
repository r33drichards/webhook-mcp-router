# Proposed NixOS Keycloak issuer (not deployed)

No host, domain, realm or release pin is selected. Review the selected host's pinned nixpkgs Keycloak module/package before enabling it. Use services.keycloak with PostgreSQL persistence, a stable HTTPS hostname, and explicitly reviewed reverse-proxy/forwarded-header settings. Store database/bootstrap credentials through that host's approved secret facility; never Nix store text, repository files or generated realm exports containing secrets. Plan backups, upgrades, signing-key rotation and monitoring. Do not copy a generic proxy/firewall configuration into a live host without review.

Pre-register one confidential service client per authorized service. Enable client authentication and service accounts; disable interactive/direct-access flows unless independently required. Configure router audience and restricted service-account scopes/roles. Record exact issuer, client ID, service-account subject and internal tenant mapping. Client secret is delivered to its service through an approved secret channel; the router only needs issuer signing keys and the non-secret mapping. No dynamic registration required.

Suggested non-secret configuration shape (placeholders, not usable deployment):

```json
{
  "issuer": "https://KEYCLOAK_HOST/realms/ROUTER_REALM",
  "audience": "webhook-mcp-router",
  "jwks": "https://KEYCLOAK_HOST/realms/ROUTER_REALM/protocol/openid-connect/certs",
  "clients": [{"clientId":"REGISTERED_SERVICE", "subject":"EXACT_SERVICE_ACCOUNT_SUBJECT", "tenantId":"tenant-example", "scopes":["router:read","requests:read"]}]
}
```

RS256 is the current implementation's explicit algorithm allowlist. Match issuer signing configuration to it; unsupported algorithms fail closed. Mapping changes currently require replacing/reloading trusted configuration; no client-admin API is exposed. Permission names must match actual Keycloak token scope contents. Review actual token fixtures without printing live tokens. The request explorer does not grant policies:write.

Approval gates: selected NixOS host, release pin, hostname/TLS, database/backup resources, deployment, client registration and credential distribution, network and role changes. Azure billing/resource approvals remain separate. Nothing here applies infrastructure changes.
