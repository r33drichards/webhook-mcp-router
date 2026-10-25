"""Actual compiled service tests in Wasmer, with an independent synthetic HTTPS host."""
import http.server,json,os,pathlib,ssl,subprocess,sys,tempfile,threading,time,socketserver,struct

failures=[]
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
        class DNS(socketserver.BaseRequestHandler):
            queries=0
            def handle(self):
                prefix=self.request.recv(2)
                if len(prefix)!=2:return
                size=struct.unpack('!H',prefix)[0];packet=b''
                while len(packet)<size:
                    part=self.request.recv(size-len(packet))
                    if not part:return
                    packet+=part
                if len(packet)<17:return
                pos=12
                while pos<len(packet) and packet[pos]:pos+=1+packet[pos]
                end=pos+5
                if end>len(packet):return
                kind=struct.unpack('!H',packet[pos+1:pos+3])[0]
                type(self).queries+=1
                # Controlled A answer only; AAAA gets a valid empty answer.
                answer=b'\xc0\x0c'+struct.pack('!HHIH',1,1,30,4)+b'\x7f\x00\x00\x01' if kind==1 else b''
                reply=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(kind==1),0,0)+packet[12:end]+answer
                self.request.sendall(struct.pack("!H",len(reply))+reply)
        dns=socketserver.ThreadingTCPServer(('127.0.0.1',0),DNS)
        dns_port=dns.server_address[1]
        threading.Thread(target=dns.serve_forever,daemon=True).start()
        for mode in ['ip','tcp-dns']:
            before=len(Sink.receipts)
            rule='ipv4:allow=127.0.0.1:{'+str(port)+','+str(dns_port)+'}/out' if mode=='tcp-dns' else 'ipv4:allow=127.0.0.1:'+str(port)+'/out'
            host='localhost' if mode=='tcp-dns' else '127.0.0.1'
            cmd=['wasmer','run','--net='+rule,'--mapdir','/fixtures:'+str(root),
                 '--env','POC_CA_FILE=/fixtures/cert.pem','--env','POC_NETWORK_TEST_URL=https://'+host+':'+str(port)]
            if mode=='tcp-dns':cmd+=['--env','POC_DNS_SERVER=127.0.0.1:'+str(dns_port)]
            cmd+=[tests,'--','-test.run','^TestGuestNetwork$','-test.v']
            try:
                result=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
                print(json.dumps(dict(stage='actual-service-'+mode,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)),flush=True)
                if result.returncode!=0 or Sink.receipts[before:]!=[b'synthetic-nonce']*5:failures.append(mode)
                if mode=='tcp-dns' and DNS.queries==0:failures.append('DNS fixture not queried')
            except subprocess.TimeoutExpired:
                print('FAIL timed out: '+mode,flush=True);failures.append(mode)
        dns.shutdown();dns.server_close();server.shutdown()
    for script in ['ci/sdk-cgi-check.py','ci/events-cgi-check.py']:
        result=subprocess.run([sys.executable,script,service])
        if result.returncode:failures.append(script)
    if failures:raise SystemExit('FAIL stages: '+', '.join(failures))
    print('PASS actual service fork IP/TCP-DNS/TLS/concurrency/cancellation and fresh-guest SDK/events/OPA checks; no managed Edge claim')
