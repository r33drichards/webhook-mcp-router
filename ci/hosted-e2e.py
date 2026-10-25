"""Real network assertions for the FUTURE reviewed synthetic test contract.

These tool/receipt names are POC-specific, not core MCP or an existing service.
Missing endpoints fail; this script never substitutes a local simulation.
"""
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect refused')


def request(url, token, value=None, protocol=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError('reviewed HTTPS endpoint required')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}
    if protocol:
        headers['MCP-Protocol-Version'] = protocol
    if value is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=headers,
        data=None if value is None else json.dumps(value).encode())
    # Separate HTTP connection each invocation; server WCGI mode must also be verified.
    with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
        if response.headers.get('Mcp-Session-Id'):
            raise RuntimeError('stateless fixture unexpectedly requires session')
        raw = response.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('oversized response')
        return json.loads(raw) if raw else None


def main():
    url, receipt_url, token, receipt_token = [os.environ[k] for k in
        ('POC_MCP_URL', 'POC_RECEIPTS_URL', 'POC_TEST_TOKEN', 'POC_RECEIPT_TOKEN')]
    if not all((url, receipt_url, token, receipt_token)):
        raise RuntimeError('missing protected configuration')
    protocol = None
    def rpc(method, params):
        value = request(url, token, {'jsonrpc': '2.0', 'id': 1,
                                     'method': method, 'params': params}, protocol)
        if value.get('error') or value.get('id') != 1:
            raise RuntimeError('RPC failure: ' + method)
        return value['result']
    init = rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                             'clientInfo': {'name': 'synthetic-ci', 'version': '0.1'}})
    protocol = init['protocolVersion']
    if protocol != '2025-06-18':
        raise RuntimeError('fixture protocol negotiation requires review')
    request(url, token, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, protocol)
    tools = {t['name'] for t in rpc('tools/list', {})['tools']}
    required = {'synthetic_subscription_create', 'synthetic_subscription_list',
                'synthetic_emit', 'synthetic_subscription_delete'}
    if not required <= tools:
        raise RuntimeError('missing reviewed synthetic fixture tools')
    def call(name, arguments):
        result = rpc('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise RuntimeError('tool failed: ' + name)
        return result['structuredContent']
    sid, nonce = 'sub_ci_' + secrets.token_hex(8), secrets.token_hex(16)
    created = False
    try:
        result = call('synthetic_subscription_create', {'id': sid})
        created = True
        if result.get('id') != sid or result.get('status') != 'active':
            raise RuntimeError('subscription not active')
        if sid not in call('synthetic_subscription_list', {})['ids']:
            raise RuntimeError('fresh invocation lost registration')
        # Destination is configured server-side; no callback URL accepted from CI.
        sent = call('synthetic_emit', {'subscription_id': sid, 'nonce': nonce})
        event_id = sent['event_id']
        for _ in range(12):
            query = urllib.parse.urlencode({'event_id': event_id})
            receipt = request(receipt_url + '?' + query, receipt_token)
            if receipt.get('received'):
                if not (receipt.get('subscription_id') == sid and receipt.get('event_id') == event_id
                        and receipt.get('nonce') == nonce and receipt.get('signature_verified') is True):
                    raise RuntimeError('receipt identity/signature assertion failed')
                print('PASS: hosted initialize/list/create/readback and controlled signed receipt')
                return
            time.sleep(2)
        raise RuntimeError('no real callback receipt')
    finally:
        if created:
            call('synthetic_subscription_delete', {'id': sid})


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # HTTP exceptions can include URLs or response data; never print secrets.
        print('FAIL: hosted synthetic E2E assertion; inspect controlled service diagnostics', file=sys.stderr)
        sys.exit(1)
