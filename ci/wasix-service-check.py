"""Actual compiled service tests in Wasmer, with an independent synthetic HTTPS host."""
import http.server,json,os,pathlib,ssl,subprocess,sys,tempfile,threading,time

service, tests = map(lambda p: str(pathlib.Path(p).resolve()),sys.argv[1:3])
with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1'],check=True,capture_output=True)
    class Sink(http.server.BaseHTTPRequestHandler):
        receipts=[]
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0'))
            if n>128: self.send_error(413); return
            body=self.rfile.read(n);type(self).receipts.append(body)
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/slow': time.sleep(2)
            self.send_response(200);self.end_headers()
        def log_message(self,*args):pass
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),Sink) as server:
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(root/'cert.pem',root/'key.pem');server.socket=tls.wrap_socket(server.socket,server_side=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        port=server.server_address[1]
        cmd=['wasmer','run','--net=ipv4:allow=127.0.0.1:'+str(port)+'/out','--mapdir','/fixtures:'+str(root),
             '--env','POC_CA_FILE=/fixtures/cert.pem','--env','POC_NETWORK_TEST_URL=https://localhost:'+str(port),
             tests,'--','-test.run','^TestGuestNetwork$','-test.v']
        result=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
        print(json.dumps(dict(stage='actual-service-network-tests',exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)),flush=True)
        assert result.returncode==0,'actual service networking tests failed'
        assert Sink.receipts==[b'synthetic-nonce']*5,'independent host did not receive all concurrent requests'
        server.shutdown()
    subprocess.run([sys.executable,'ci/sdk-cgi-check.py',service],check=True)
    subprocess.run([sys.executable,'ci/events-cgi-check.py',service],check=True)
    print('PASS actual service fork build/network suite and fresh-guest SDK persistence; no managed Edge claim')
