"""Real HTTPS assertions for the reviewed, controlled synthetic hosted fixture.

Uses the verified events/* contract and registered Rego, never a live GitHub hook.
Every call uses a fresh HTTP connection. No secrets, URLs or response bodies log.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STAGE = 'configuration'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect refused')


def endpoint(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.query):
        raise RuntimeError('reviewed HTTPS endpoint required')
    return parsed


def request(url, token=None, value=None, protocol=None, raw=None, extra=None,
            expected_status=200):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError('reviewed HTTPS endpoint required')
    headers = {'Accept': 'application/json, text/event-stream'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    if protocol:
        headers['MCP-Protocol-Version'] = protocol
    if value is not None:
        if raw is not None:
            raise RuntimeError('ambiguous request body')
        raw = json.dumps(value, separators=(',', ':')).encode()
    if raw is not None:
        headers['Content-Type'] = 'application/json'
    headers.update(extra or {})
    req = urllib.request.Request(url, headers=headers, data=raw)
    # No ambient proxies: all reviewed endpoints are contacted directly.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    try:
        response = opener.open(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        if response.status != expected_status:
            raise RuntimeError('unexpected HTTP status')
        if response.headers.get('Mcp-Session-Id'):
            raise RuntimeError('stateless fixture unexpectedly requires session')
        body = response.read(65537)
        if len(body) > 65536:
            raise RuntimeError('oversized response')
        if expected_status != 200:
            return None
        return json.loads(body) if body else None


def main():
    global STAGE
    names = ('POC_MCP_URL', 'POC_RECEIPTS_URL', 'POC_CALLBACK_URL',
             'POC_TEST_TOKEN', 'POC_RECEIPT_TOKEN', 'POC_WEBHOOK_SECRET')
    url, receipt_url, callback, token, receipt_token, secret = [os.environ[k] for k in names]
    if not all((url, receipt_url, callback, token, receipt_token, secret)):
        raise RuntimeError('missing protected configuration')
    parsed = endpoint(url)
    endpoint(receipt_url)
    endpoint(callback)
    ingress_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '/hooks/github', '', ''))
    if not secret.startswith('whsec_'):
        raise RuntimeError('invalid synthetic signing configuration')
    key = base64.b64decode(secret[6:], validate=True)
    if not 24 <= len(key) <= 64 or base64.b64encode(key).decode() != secret[6:]:
        raise RuntimeError('invalid synthetic signing configuration')
    protocol = None

    def rpc(method, params, expect_error=False):
        result = request(url, token, {'jsonrpc': '2.0', 'id': 1,
                                     'method': method, 'params': params}, protocol)
        if not isinstance(result, dict) or result.get('id') != 1:
            raise RuntimeError('RPC envelope failed')
        if expect_error:
            if not result.get('error'):
                raise RuntimeError('expected RPC rejection')
            return None
        if result.get('error') or not isinstance(result.get('result'), dict):
            raise RuntimeError('RPC failure')
        return result['result']

    def tool(name, arguments):
        result = rpc('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError') or not isinstance(result.get('structuredContent'), dict):
            raise RuntimeError('tool failure')
        return result['structuredContent']

    STAGE = 'initialize-and-catalog'
    init = rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                             'clientInfo': {'name': 'synthetic-ci', 'version': '0.2'}})
    protocol = init['protocolVersion']
    if protocol != '2025-06-18' or init.get('capabilities', {}).get('events') != {}:
        raise RuntimeError('fixture capability/protocol mismatch')
    catalog = rpc('events/list', {})['events']
    definition = next(e for e in catalog if e['name'] == 'webhook.received')
    if definition.get('delivery') != ['webhook'] or definition['inputSchema']['type'] != 'object':
        raise RuntimeError('event catalog mismatch')
    tools = {t['name'] for t in rpc('tools/list', {})['tools']}
    if not {'synthetic_subscription_list', 'synthetic_policy_register', 'synthetic_policy_list'} <= tools:
        raise RuntimeError('missing reviewed fixture tools')

    subscribe = {'name': 'webhook.received', 'arguments': {},
                 'delivery': {'mode': 'webhook', 'url': callback, 'secret': secret}, 'ttlMs': 300000}
    unsubscribe = {'name': 'webhook.received', 'arguments': {},
                   'delivery': {'mode': 'webhook', 'url': callback}}
    created = False
    policy_attempted = False
    policy_id = 'policy_hosted_e2e'
    nonce = secrets.token_hex(16)
    try:
        STAGE = 'reject-invalid-subscription-secret'
        bad = dict(subscribe, delivery=dict(subscribe['delivery'], secret='whsec_invalid'))
        rpc('events/subscribe', bad, expect_error=True)

        STAGE = 'signed-challenge-subscribe'
        # Mark before the request: a transport failure can leave uncertain activation.
        created = True
        result = rpc('events/subscribe', subscribe)
        sid = result['id']
        if (not isinstance(sid, str) or not sid.startswith('sub_')
                or result.get('cursor') != sid + ':0' or result.get('truncated') is not False
                or not isinstance(result.get('refreshBefore'), str)
                or 'secret' in result or 'whsec_' in json.dumps(result)):
            raise RuntimeError('subscription result contract')
        STAGE = 'fresh-subscription-readback'
        if sid not in tool('synthetic_subscription_list', {})['ids']:
            raise RuntimeError('fresh invocation lost subscription')

        STAGE = 'renew-subscription'
        renewed = rpc('events/subscribe', dict(subscribe, cursor=result['cursor']))
        if renewed.get('id') != sid or renewed.get('cursor') != result['cursor']:
            raise RuntimeError('renewal identity mismatch')

        STAGE = 'register-and-readback-rego'
        # Nonmatching input yields an empty decision rather than an undefined rule.
        # Match a per-run nonce so unrelated fixture traffic cannot trigger this route.
        source = ('package router\nimport rego.v1\ndefault routes := []\n'
                  'routes := [{"subscription_id": ' + json.dumps(sid)
                  + ', "data": {"nonce": input.nonce}}] if {\n'
                  ' input.action == "opened"\n input.repository.full_name == "synthetic/webhook-router"\n'
                  ' input.nonce == ' + json.dumps(nonce) + '\n}\n')
        policy_attempted = True
        tool('synthetic_policy_register', {'id': policy_id, 'source': source})
        persisted = next(p for p in tool('synthetic_policy_list', {})['policies'] if p['id'] == policy_id)
        if persisted['source'] != source:
            raise RuntimeError('fresh invocation lost policy')

        def ingress(action, valid=True):
            event = {'action': action, 'number': 1, 'nonce': nonce,
                     'repository': {'full_name': 'synthetic/webhook-router'},
                     'pull_request': {'number': 1, 'title': 'Synthetic runtime fixture'}}
            raw = json.dumps(event, separators=(',', ':')).encode()
            signature = 'sha256=' + hmac.new(key, raw, hashlib.sha256).hexdigest()
            return request(ingress_url, raw=raw, extra={
                'X-Hub-Signature-256': signature if valid else 'sha256=' + '0' * 64,
                'X-GitHub-Event': 'pull_request', 'X-GitHub-Delivery': secrets.token_hex(16)},
                expected_status=200 if valid else 401)

        STAGE = 'reject-invalid-ingress-signature'
        ingress('opened', valid=False)
        STAGE = 'nonmatching-policy'
        nonmatch = next(p for p in ingress('closed')['policies'] if p['policy_id'] == policy_id)
        if nonmatch.get('error') or nonmatch.get('routes') != []:
            raise RuntimeError('nonmatching event routed')

        STAGE = 'signed-github-shaped-ingress'
        matched = next(p for p in ingress('opened')['policies'] if p['policy_id'] == policy_id)
        routes = matched.get('routes', [])
        if matched.get('error') or len(routes) != 1 or routes[0].get('subscription_id') != sid:
            raise RuntimeError('policy route mismatch')
        event_id = routes[0].get('event_id')
        if not event_id:
            raise RuntimeError('delivery event identity missing')

        STAGE = 'signed-callback-receipt-readback'
        for _ in range(8):
            query = urllib.parse.urlencode({'event_id': event_id})
            receipt = request(receipt_url + '?' + query, receipt_token)
            if receipt.get('received'):
                if not (receipt.get('subscription_id') == sid and receipt.get('event_id') == event_id
                        and receipt.get('nonce') == nonce and receipt.get('signature_verified') is True):
                    raise RuntimeError('receipt identity/signature mismatch')
                # A second connection confirms readback is not request-local state.
                if request(receipt_url + '?' + query, receipt_token) != receipt:
                    raise RuntimeError('fresh receipt readback changed')
                break
            time.sleep(2)
        else:
            raise RuntimeError('no real callback receipt')

        STAGE = 'unsubscribe-and-inactive-route'
        rpc('events/unsubscribe', unsubscribe)
        rpc('events/unsubscribe', unsubscribe)
        if sid in tool('synthetic_subscription_list', {})['ids']:
            raise RuntimeError('subscription survived unsubscribe')
        inactive = next(p for p in ingress('opened')['policies'] if p['policy_id'] == policy_id)
        if inactive.get('routes') != [] or not inactive.get('error'):
            raise RuntimeError('unsubscribed destination remained eligible')
        created = False
    finally:
        failed_stage = STAGE
        cleanup_failed = False
        if policy_attempted:
            try:
                tool('synthetic_policy_register', {'id': policy_id,
                     'source': 'package router\nimport rego.v1\nroutes := []\n'})
            except Exception:
                cleanup_failed = True
        if created:
            try:
                rpc('events/unsubscribe', unsubscribe)
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            print('FAIL: hosted synthetic cleanup; controlled registration/policy may remain', file=sys.stderr)
            if sys.exc_info()[0] is None:
                STAGE = 'cleanup'
                raise RuntimeError('cleanup failed')
        STAGE = failed_stage
    print('PASS: hosted events catalog/challenge/subscribe/renew/unsubscribe; fresh state; signed ingress/Rego route/signed callback receipt')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAIL: hosted synthetic E2E stage=' + STAGE + '; details withheld', file=sys.stderr)
        sys.exit(1)
