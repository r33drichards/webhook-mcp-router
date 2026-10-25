"""Fresh Wasmer CGI guest probes with no credentials or mounted state."""
import json,pathlib,subprocess,sys
wasm=str(pathlib.Path(sys.argv[1]).resolve())
for method,path,status,expected in [('GET','/_poc/health',200,{'status':'runtime-ready'}),('GET','/mcp',503,{'error':'POC_SIGNING_CONFIG_INVALID'})]:
    env={'REQUEST_METHOD':method,'SERVER_PROTOCOL':'HTTP/1.1','SERVER_NAME':'localhost',
         'SERVER_PORT':'80','GATEWAY_INTERFACE':'CGI/1.1','SCRIPT_NAME':path,'REQUEST_URI':path,'CONTENT_LENGTH':'0'}
    command=['wasmer','run',wasm]
    for name,value in env.items():command+=['--env',name+'='+value]
    result=subprocess.run(command,input='',text=True,capture_output=True,timeout=60)
    assert result.returncode==0, 'guest exited before CGI reply'
    headers,body=result.stdout.split('\n\n',1)
    assert 'Status: '+str(status) in headers and json.loads(body)==expected, 'startup response mismatch'
    print(json.dumps({'path':path,'status':status,'body':expected,'exit_code':result.returncode}))
print('PASS credential-free Wasmer CGI startup; no hosted claim')
