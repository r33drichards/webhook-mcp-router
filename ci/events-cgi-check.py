"""Actual official SDK + OPA guest, fresh Wasmer invocation per request and real TLS sink."""
import base64,hashlib,hmac,http.server,json,pathlib,secrets,ssl,subprocess,sys,tempfile,threading,time

wasm=str(pathlib.Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp)
    for name in ['state','receipts']: (root/name).mkdir()
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,capture_output=True)
    key=secrets.token_bytes(32);token=secrets.token_hex(32)
    class Sink(http.server.BaseHTTPRequestHandler):
        events=[]; challenges=0
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0'))
            if n>4096:self.send_error(413);return
            raw=self.rfile.read(n);eid=self.headers.get('webhook-id','');stamp=self.headers.get('webhook-timestamp','')
            expected='v1,'+base64.b64encode(hmac.new(key,(eid+'.'+stamp+'.').encode()+raw,hashlib.sha256).digest()).decode()
            if not hmac.compare_digest(expected,self.headers.get('webhook-signature','')) or abs(int(stamp)-int(time.time()))>300:self.send_error(401);return
            event=json.loads(raw)
            if event.get('type')=='verification':
                type(self).challenges+=1;body=json.dumps({'challenge':event['challenge']}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            else:
                assert event['eventId']==eid and event['name']=='webhook.received'
                type(self).events.append((self.headers['X-MCP-Subscription-Id'],event))
                self.send_response(204);self.end_headers()
        def log_message(self,*args):pass
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),Sink) as server:
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(root/'cert.pem',root/'key.pem');server.socket=tls.wrap_socket(server.socket,server_side=True)
        threading.Thread(target=server.serve_forever,daemon=True).start();port=server.server_address[1]
        callback='https://127.0.0.1:'+str(port)+'/callback'
        secret='whsec_'+base64.b64encode(key).decode()
        common=dict(POC_STATE_DIR='/state',POC_RECEIPT_DIR='/receipts',POC_TEST_TOKEN=token,POC_RECEIPT_TOKEN=secrets.token_hex(32),POC_CALLBACK_URL=callback,POC_WEBHOOK_SECRET=secret,POC_CA_FILE='/fixtures/cert.pem',REQUEST_METHOD='POST',SERVER_PROTOCOL='HTTP/1.1',SERVER_NAME='localhost',SERVER_PORT='80',GATEWAY_INTERFACE='CGI/1.1',CONTENT_TYPE='application/json',HTTP_ACCEPT='application/json, text/event-stream',HTTP_AUTHORIZATION='Bearer '+token,HTTP_MCP_PROTOCOL_VERSION='2025-06-18')
        def request(path,value,headers=None):
            body=json.dumps(value);env=dict(common,CONTENT_LENGTH=str(len(body)),SCRIPT_NAME=path,REQUEST_URI=path)
            if headers:env.update(headers)
            cmd=['wasmer','run','--net=ipv4:allow=127.0.0.1:'+str(port)+'/out',wasm]
            for name in ['state','receipts']:cmd+=['--mapdir','/'+name+':'+str(root/name)]
            cmd+=['--mapdir','/fixtures:'+str(root)]
            for name,value in env.items():cmd+=['--env',name+'='+value]
            try:
                result=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=60)
            except subprocess.TimeoutExpired:
                raise RuntimeError("CGI guest timed out; request environment withheld") from None
            assert result.returncode==0,'CGI guest failed before response'
            head,payload=result.stdout.split('\n\n',1)
            assert 'mcp-session-id:' not in head.lower()
            return head,payload
        def rpc(method,params,expect_error=False):
            head,payload=request('/mcp',dict(jsonrpc='2.0',id=1,method=method,params=params))
            assert 'Status: 200 OK' in head,(method,head)
            data=json.loads(payload)
            if expect_error:assert 'error' in data;return
            assert 'error' not in data,(method,data.get('error'))
            return data['result']
        def tool(name,args):
            result=rpc('tools/call',dict(name=name,arguments=args));assert not result.get('isError'),name
            return result['structuredContent']
        init=rpc('initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='synthetic',version='1')))
        assert 'events' in init['capabilities']
        assert rpc('events/list',{})['events'][0]['name']=='webhook.received'
        params=dict(name='webhook.received',arguments={},delivery=dict(mode='webhook',url=callback,secret=secret),ttlMs=60000)
        subscribed=rpc('events/subscribe',params);sid=subscribed['id'];assert Sink.challenges==1
        assert sid in tool('synthetic_subscription_list',{})['ids'],'fresh instance lost grant'
        nonce=secrets.token_hex(16)
        tool('synthetic_emit',dict(subscription_id=sid,nonce=nonce));assert Sink.events[-1][0]==sid and Sink.events[-1][1]['data']['nonce']==nonce
        source='package router\nimport rego.v1\nroutes := [{"subscription_id": "'+sid+'", "data": {"nonce": input.nonce}}] if { input.action == "opened" }\n'
        tool('synthetic_policy_register',dict(id='policy_match',source=source))
        assert len(tool('synthetic_policy_list',{})['policies'])==1
        value=dict(action='opened',nonce=nonce);body=json.dumps(value).encode();sig='sha256='+hmac.new(key,body,hashlib.sha256).hexdigest()
        head,payload=request('/hooks/github',value,{'HTTP_X_HUB_SIGNATURE_256':sig})
        assert 'Status: 200 OK' in head and len(Sink.events)==2
        routed=json.loads(payload)['policies'][0];assert not routed.get('error') and routed['routes'][0]['subscription_id']==sid
        head,_=request('/hooks/github',value,{'HTTP_X_HUB_SIGNATURE_256':'sha256=bad'});assert '401' in head and len(Sink.events)==2
        params['cursor']=subscribed['cursor'];renewed=rpc('events/subscribe',params);assert renewed['id']==sid and Sink.challenges==2
        unsubscribe=dict(name=params['name'],arguments={},delivery=dict(mode='webhook',url=callback))
        rpc('events/unsubscribe',unsubscribe);rpc('events/unsubscribe',unsubscribe)
        assert sid not in tool('synthetic_subscription_list',{})['ids']
        print('PASS Wasmer guest official SDK events discovery/challenge/subscribe/fresh-readback/renew/unsubscribe + signed ingress/native OPA/independent HTTPS signed receipt',flush=True)
        server.shutdown()
