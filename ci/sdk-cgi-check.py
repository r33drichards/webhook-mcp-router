"""Run official SDK CGI Wasm in a fresh Wasmer instance per RPC; no network."""
import base64
import json
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile

wasm = str(pathlib.Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / 'state').mkdir()
    (root / 'receipts').mkdir()
    token = secrets.token_hex(32)
    common = dict(POC_STATE_DIR='/state', POC_RECEIPT_DIR='/receipts', POC_TEST_TOKEN=token,
                  POC_RECEIPT_TOKEN=secrets.token_hex(32), POC_CALLBACK_URL='https://synthetic.invalid/callback',
                  POC_WEBHOOK_SECRET='whsec_' + base64.b64encode(secrets.token_bytes(32)).decode(),
                  REQUEST_METHOD='POST', SERVER_PROTOCOL='HTTP/1.1', SERVER_NAME='localhost',
                  SERVER_PORT='80', GATEWAY_INTERFACE='CGI/1.1', SCRIPT_NAME='/mcp', REQUEST_URI='/mcp',
                  CONTENT_TYPE='application/json', HTTP_ACCEPT='application/json, text/event-stream',
                  HTTP_AUTHORIZATION='Bearer ' + token, HTTP_MCP_PROTOCOL_VERSION='2025-06-18')
    def rpc(method, params):
        body = json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params))
        cmd = ['wasmer', 'run', wasm, '--mapdir', '/state:' + str(root / 'state'),
               '--mapdir', '/receipts:' + str(root / 'receipts')]
        for key, value in dict(common, CONTENT_LENGTH=str(len(body))).items():
            cmd += ['--env', key + '=' + value]
        try:
            p = subprocess.run(cmd, input=body, text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise RuntimeError("CGI guest timed out; request environment withheld") from None
        if p.returncode:
            raise RuntimeError('SDK CGI guest failed: ' + method)
        headers, payload = p.stdout.split('\n\n', 1)
        assert 'Status: 200 OK' in headers and 'mcp-session-id:' not in headers.lower()
        data = json.loads(payload)
        assert 'error' not in data and data['id'] == 1, method
        return data['result']
    rpc('initialize', dict(protocolVersion='2025-06-18', capabilities={}, clientInfo=dict(name='synthetic', version='1')))
    names = {t['name'] for t in rpc('tools/list', {})['tools']}
    assert 'synthetic_subscription_create' in names
    sid = 'sub_ci_' + secrets.token_hex(8)
    created = rpc('tools/call', dict(name='synthetic_subscription_create', arguments=dict(id=sid)))
    assert created.get('isError') is not True
    listing = rpc('tools/call', dict(name='synthetic_subscription_list', arguments={}))
    assert sid in listing['structuredContent']['ids']
    print('PASS: official SDK CGI guest initialize/tools/create/fresh-instance readback; no hosted/outbound claim')
