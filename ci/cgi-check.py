"""Guest CGI assertions only: does not claim HTTP-host/MCP compatibility."""
import json
import os
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as directory:
    wasm = directory + '/cgi.wasm'
    subprocess.run(['go', 'build', '-o', wasm, 'spike/wcgi/main.go'],
                   env=dict(os.environ, GOOS='wasip1', GOARCH='wasm'), check=True)
    body = '{"synthetic":true}\n'
    command = ['wasmer', 'run', wasm]
    for key, value in dict(REQUEST_METHOD='POST', SERVER_PROTOCOL='HTTP/1.1',
                          SERVER_NAME='localhost', SERVER_PORT='80',
                          GATEWAY_INTERFACE='CGI/1.1', REQUEST_URI='/synthetic',
                          SCRIPT_NAME='/synthetic', CONTENT_TYPE='application/json',
                          CONTENT_LENGTH=str(len(body)), HTTP_X_SYNTHETIC='fixture-only').items():
        command += ['--env', key + '=' + value]
    result = subprocess.run(command, input=body, text=True, capture_output=True,
                            check=True, timeout=45)
    headers, payload = result.stdout.split('\n\n', 1)
    assert 'Status: 200 OK' in headers
    assert json.loads(payload) == dict(method='POST', path='/synthetic', body=body,
                                       synthetic_header='fixture-only')
    print('PASS: Go CGI guest method/path/body/header. Not hosted MCP.')
