"""Synthetic host loopback HTTP/TCP controls and actual Wasmer guest probes."""
import hashlib, http.server, json, os, pathlib, socketserver, subprocess, threading
base=pathlib.Path(__file__).resolve().parent
root=base.parents[1]
env=os.environ.copy()
env.update(GOTOOLCHAIN='local',GOPATH=str(root/'.tools/gopath'),GOMODCACHE=str(root/'.tools/gomodcache'),GOCACHE=str(root/'.tools/gocache'),WASMER_DIR=str(root/'.tools/wasmer'))
logs=[]

def run(cmd,environment=env):
 r=subprocess.run(cmd,cwd=base,text=True,capture_output=True,env=environment,timeout=90)
 entry={'command':cmd,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 logs.append(entry);print(json.dumps(entry),flush=True);return r

try:
 for target,extra in [('probe-native',{}),('probe.wasm',{'GOOS':'wasip1','GOARCH':'wasm'})]:
  child=env.copy();child.update(extra)
  r=run([str(root/'.tools/go/bin/go'),'build','-o',target,'./probe'],child)
  assert r.returncode==0

 class HTTP(http.server.BaseHTTPRequestHandler):
  requests=0
  def do_GET(self):
   type(self).requests+=1
   self.send_response(200);self.end_headers();self.wfile.write(b'synthetic-host-http')
  def log_message(self,*args):pass
 class TCP(socketserver.BaseRequestHandler):
  requests=0
  def handle(self):
   type(self).requests+=1
   body=self.request.recv(128);self.request.sendall(body)

 with http.server.ThreadingHTTPServer(('127.0.0.1',0),HTTP) as httpd, socketserver.ThreadingTCPServer(('127.0.0.1',0),TCP) as tcpd:
  for server in [httpd,tcpd]:threading.Thread(target=server.serve_forever,daemon=True).start()
  for mode,server,handler in [('outbound-http',httpd,HTTP),('outbound-tcp',tcpd,TCP)]:
   address='127.0.0.1:'+str(server.server_address[1])
   native=run([str(base/'probe-native'),mode,address]);assert native.returncode==0
   before=handler.requests
   guest=run([str(root/'.tools/wasmer/bin/wasmer'),'run','--net=ipv4:allow='+address+'/out',str(base/'probe.wasm'),'--',mode,address])
   expected=45 if mode=='outbound-http' else 47
   assert guest.returncode==expected,(guest.returncode,guest.stdout,guest.stderr)
   assert handler.requests==before,'Guest unexpectedly reached host; revise conclusion'
   logs.append({'mode':mode,'native_host_requests':before,'host_requests_after_guest':handler.requests,'assertions':'native passed; guest failed; guest made no host connection'})
  httpd.shutdown();tcpd.shutdown()
 logs.append({'artifact':'probe.wasm','sha256':hashlib.sha256((base/'probe.wasm').read_bytes()).hexdigest()})
finally:
 (base/'logs/outbound-runtime.json').write_text(json.dumps({'environment':{k:env[k] for k in ['GOTOOLCHAIN','GOPATH','GOMODCACHE','GOCACHE','WASMER_DIR']},'records':logs},indent=2)+'\n')
