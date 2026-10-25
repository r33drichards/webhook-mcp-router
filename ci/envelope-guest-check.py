import json,pathlib,subprocess,sys
wasm=str(pathlib.Path(sys.argv[1]).resolve())
for method,body in [('GET',''),('POST','Synthetic'),(None,'')]:
    env={'SCRIPT_NAME':'rust_wcgi','SERVER_PROTOCOL':'HTTP/1.1','GATEWAY_INTERFACE':'CGI/1.1','CONTENT_LENGTH':str(len(body))}
    if method:env['REQUEST_METHOD']=method
    cmd=['wasmer','run',wasm]
    for k,v in env.items():cmd+=['--env',k+'='+v]
    result=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=30)
    assert result.returncode==0
    headers,payload=result.stdout.split('\n\n',1);value=json.loads(payload)
    assert 'Status: 200 OK' in headers
    assert value['request_method_present']==bool(method)
    assert value['method_is_get']==(method=='GET') and value['method_is_post']==(method=='POST')
    assert value['stdin_synthetic']==(body=='Synthetic')
    assert 'CGI_ENVELOPE_PROBE' in result.stderr
    print(json.dumps({'stage':'guest-envelope','supplied_method':method,'report':value}))
