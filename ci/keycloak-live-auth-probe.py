"""Approved-scope candidate: token issuance and read-only Admin API probes only."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = 'https://keycloak-production-295b.up.railway.app'
ISSUER = ORIGIN + '/realms/webhook-router'
GITHUB_ISSUER = 'https://token.actions.githubusercontent.com'
SUBJECT = 'repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:keycloak-router-admin'
CLIENT = 'terraform-webhook-router'
WORKFLOW = 'r33drichards/webhook-mcp-router/.github/workflows/keycloak-router-admin.yml@refs/heads/main'
LIMIT = 262144

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

# Default TLS verification; never follow a redirect carrying an Authorization header.
http = urllib.request.build_opener(NoRedirect())

def request(url, token=None, form=None):
    if urllib.parse.urlparse(url).scheme != 'https':
        raise RuntimeError('HTTPS_REQUIRED')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if form is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, headers=headers, data=data)
    try:
        with http.open(req, timeout=15) as response:
            body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise RuntimeError('RESPONSE_TOO_LARGE')
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        # Never include remote bodies, token request URLs, or headers in diagnostics.
        return error.code, None

def check(name, condition):
    if not condition:
        print('FAIL ' + name, flush=True)
        raise RuntimeError('PROBE_ASSERTION_FAILED')
    print('PASS ' + name, flush=True)

def claims(token):
    if not isinstance(token, str) or len(token) > 32768:
        raise RuntimeError('TOKEN_SHAPE')
    parts = token.split('.')
    if len(parts) != 3:
        raise RuntimeError('TOKEN_SHAPE')
    return json.loads(base64.urlsafe_b64decode(parts[1] + '==='))

def assertion(audience=ISSUER):
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    # Use GitHub's injected endpoint, keeping it and its bearer out of all output.
    separator = '&' if '?' in url else '?'
    status, data = request(url + separator + 'audience=' + urllib.parse.quote(audience, safe=''),
                           os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN'])
    check('GITHUB_ISSUANCE', status == 200 and isinstance(data, dict))
    jwt = data['value']
    p = claims(jwt)
    expected = {
        'iss': GITHUB_ISSUER, 'sub': SUBJECT, 'aud': audience,
        'repository': 'r33drichards/webhook-mcp-router',
        'repository_id': '1432792940', 'repository_owner_id': '57335981',
        'ref': 'refs/heads/main', 'workflow_ref': WORKFLOW,
        'environment': 'keycloak-router-admin', 'event_name': 'workflow_dispatch',
    }
    check('EXACT_GITHUB_CONTEXT', all(str(p.get(k)) == v for k, v in expected.items()))
    # Payload inspection is a context guard, not signature validation. Keycloak validates JWKS.
    return jwt

def exchange(jwt):
    return request(ISSUER + '/protocol/openid-connect/token', form={
        'grant_type': 'client_credentials', 'client_id': CLIENT,
        'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
        'client_assertion': jwt,
    })

def run():
    check('WORKFLOW_CONTEXT', os.environ.get('GITHUB_REPOSITORY') == 'r33drichards/webhook-mcp-router'
          and os.environ.get('GITHUB_REF') == 'refs/heads/main'
          and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
          and os.environ.get('GITHUB_WORKFLOW_REF') == WORKFLOW)
    status, discovery = request(ISSUER + '/.well-known/openid-configuration')
    check('LIVE_ISSUER_DISCOVERY', status == 200 and discovery.get('issuer') == ISSUER
          and discovery.get('token_endpoint') == ISSUER + '/protocol/openid-connect/token')
    jwt = assertion()
    status, result = exchange(jwt)
    check('LIVE_FEDERATED_EXCHANGE', status == 200 and isinstance(result, dict))
    token = result['access_token']
    p = claims(token)
    check('SHORT_LIVED_MANAGER_IDENTITY', p.get('iss') == ISSUER and p.get('azp') == CLIENT
          and isinstance(p.get('sub'), str) and 0 < p.get('exp', 0) - p.get('iat', 0) <= 90)
    roles = p.get('resource_access', {}).get('realm-management', {}).get('roles', [])
    check('EXACT_MANAGEMENT_ROLE', set(roles) == {'manage-clients'})
    status, clients = request(ORIGIN + '/admin/realms/webhook-router/clients?clientId=' + CLIENT, token)
    check('OWN_CLIENT_READ', status == 200 and isinstance(clients, list)
          and len(clients) == 1 and clients[0].get('clientId') == CLIENT)
    client_id = urllib.parse.quote(clients[0]['id'], safe='')
    status, account = request(ORIGIN + '/admin/realms/webhook-router/clients/' + client_id + '/service-account-user', token)
    check('SERVICE_ACCOUNT_SUBJECT', status == 200 and account.get('id') == p['sub'])
    for realm in ('mcp', 'master'):
        status, _ = request(ORIGIN + '/admin/realms/' + realm + '/clients', token)
        check('DENY_' + realm.upper() + '_ADMIN_READ', status == 403)
    check('ASSERTION_REPLAY_DENIED', exchange(jwt)[0] in (400, 401))
    check('WRONG_AUDIENCE_DENIED', exchange(assertion('https://wrong-audience.example.invalid'))[0] in (400, 401))
    print('PASS live authentication/read-only boundary probe; no Terraform or Admin API mutation', flush=True)

if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        # Exception types only: urllib/JSON details could contain sensitive URL/body data.
        print('FAIL live authentication probe (' + type(error).__name__ + ')', flush=True)
        raise SystemExit(1)
