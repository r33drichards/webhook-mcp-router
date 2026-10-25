"""Synthetic host TCP/TLS/HTTP validation of existing WASIX Go fork."""
import http.server,json,os,pathlib,socketserver,ssl,subprocess,tempfile,threading
with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,capture_output=True)
    go=os.environ['WASIX_GO']
    subprocess.run([go,'version'],check=True)
    subprocess.run([go,'build','-o',str(root/'probe.wasm'),'spike/prior-art/main.go'],env=dict(os.environ,GOTOOLCHAIN='local',GOOS='wasip1',GOARCH='wasm',CGO_ENABLED='0',GO111MODULE='off'),check=True)
    subprocess.run(['wasmer','inspect',str(root/'probe.wasm')],check=True)
    class TCP(socketserver.BaseRequestHandler):
        calls=0
        def handle(self):
            type(self).calls+=1;self.request.sendall(self.request.recv(128))
    class HTTP(http.server.BaseHTTPRequestHandler):
        receipts=[]
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0'))
            if n>128:self.send_error(413);return
            body=self.rfile.read(n);type(self).receipts.append(body)
            self.send_response(200);self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    with socketserver.ThreadingTCPServer(('127.0.0.1',0),TCP) as tcp,http.server.ThreadingHTTPServer(('127.0.0.1',0),HTTP) as https:
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem');https.socket=ctx.wrap_socket(https.socket,server_side=True)
        for server in [tcp,https]:threading.Thread(target=server.serve_forever,daemon=True).start()
        for mode in ['tcp','tls','untrusted','wrong-name','https']:
            addr='127.0.0.1:'+str((tcp if mode=='tcp' else https).server_address[1])
            cmd=['wasmer','run','--net=ipv4:allow='+addr+'/out','--mapdir','/fixtures:'+str(root),str(root/'probe.wasm'),'--',mode,addr]
            result=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
            print(json.dumps(dict(stage=mode,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)),flush=True)
            assert result.returncode==0, 'existing toolchain stage failed: '+mode
        assert TCP.calls==1 and HTTP.receipts==[b'synthetic-nonce']
        print('PASS independent host TCP and HTTPS receipts; trusted TLS and negative certificate checks')
        tcp.shutdown();https.shutdown()
