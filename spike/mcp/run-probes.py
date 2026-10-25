import os, pathlib, subprocess, json, urllib.request, selectors
base=pathlib.Path(__file__).resolve().parent
wasmer='/workspace/webhook-mcp-router/.tools/wasmer/bin/wasmer'
env=os.environ.copy();env['WASMER_DIR']='/workspace/webhook-mcp-router/.tools/wasmer'
for mode,cmd in [('native',[str(base/'probe-native'),'serve']),('wasmer',[wasmer,'run','--net=ipv4:allow=127.0.0.1:18089/in',str(base/'probe.wasm'),'--','serve'])]:
 p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
 sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ)
 assert sel.select(60),'no ready marker'
 ready=p.stdout.readline().strip();assert ready.startswith('LISTENER_READY:'),ready
 try:
  with urllib.request.urlopen('http://127.0.0.1:18089',timeout=2) as r:result={'status':r.status,'body':r.read().decode()}
 except Exception as e:result={'error':str(e),'type':type(e).__name__}
 p.wait(timeout=15)
 output={'command':cmd,'ready':ready,'host_request':result,'exit_code':p.returncode,'stderr':p.stderr.read()}
 (base/'logs'/f'{mode}-host-http.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output),flush=True)
 if mode=='native':assert result=={'status':200,'body':'synthetic-ok'}
 else:assert 'error' in result,'Unexpected host reachability: inspect before updating expectation'
