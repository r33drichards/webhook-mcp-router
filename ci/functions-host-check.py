"""Real local Functions host probe. No Azure login, deployment or service credentials."""
import argparse,json,os,pathlib,subprocess,time,urllib.request,urllib.error

def request(path,body=None,headers=None):
    h={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
    h.update(headers or {})
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('http://127.0.0.1:7071'+path,data=data,headers=h)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return r.status,r.headers,r.read(262144)
    except urllib.error.HTTPError as e:return e.code,e.headers,e.read(262144)

def rpc(method,params,ident=1):return {'jsonrpc':'2.0','id':ident,'method':method,'params':params}
def message(body):
    text=body.decode('utf-8')
    if text.lstrip().startswith('{'):return json.loads(text)
    return json.loads(next(line[6:] for line in text.splitlines() if line.startswith('data: ')))
def check(ok,name):
    if not ok:raise RuntimeError(name)
    print('PASS '+name,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--func',required=True);p.add_argument('--root',required=True);p.add_argument('--log-dir',required=True);args=p.parse_args()
    folder=pathlib.Path(args.log_dir);folder.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(FUNCTIONS_WORKER_RUNTIME='dotnet-isolated',AzureWebJobsStorage='UseDevelopmentStorage=true',AzureWebJobsSecretStorageType='files',FUNCTIONS_CORE_TOOLS_TELEMETRY_OPTOUT='1')
    # No router configuration: prove fail-closed behavior, never configure an insecure auth fallback.
    env.pop('ROUTER_AUTH_JSON',None);env.pop('ROUTER_TENANTS_JSON',None)
    env['AzureWebJobs.RouterDispatch.Disabled']='true';env['AzureWebJobs.RouterReconcile.Disabled']='true'
    out=open(folder/'host.stdout.log','w',encoding='utf-8');err=open(folder/'host.stderr.log','w',encoding='utf-8')
    proc=subprocess.Popen([args.func,'start','--no-build','--script-root',os.path.abspath(args.root),'--port','7071','--address','127.0.0.1'],env=env,stdout=out,stderr=err)
    success=False
    try:
        ready=False
        for _ in range(90):
            if proc.poll() is not None:raise RuntimeError('Functions host exited '+str(proc.returncode))
            try:
                status,_,_=request('/api/mcp',{})
                if status==401:ready=True;break
            except (OSError,urllib.error.URLError,TimeoutError):pass
            time.sleep(1)
        check(ready,'actual Functions host boots and bearer route rejects missing token')
        check(request('/api/mcp',{}, {'Authorization':'Bearer synthetic-invalid-token'})[0]==503,'unconfigured issuer fails closed through host')
        check(request('/api/webhooks/unconfigured-source',{})[0]==503,'unconfigured ingress fails closed through host')
        status,headers,body=request('/runtime/webhooks/mcp',rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'host-synthetic','version':'1'}}))
        check(status==200,'host-owned MCP extension initialize HTTP200')
        check('result' in message(body),'host-owned MCP initialize protocol result')
        follow={'MCP-Protocol-Version':'2025-06-18'}
        if headers.get('Mcp-Session-Id'):follow['Mcp-Session-Id']=headers['Mcp-Session-Id']
        status,_,body=request('/runtime/webhooks/mcp',rpc('tools/list',{},2),follow)
        check(status==200 and any(t['name']=='router_status' for t in message(body)['result']['tools']),'host-owned MCP tools/list')
        status,_,body=request('/runtime/webhooks/mcp',rpc('tools/call',{'name':'router_status','arguments':{}},3),follow)
        check(status==200 and not message(body).get('result',{}).get('isError',False) and 'result' in message(body),'host-owned MCP readiness tools/call')
        success=True
        print('LIMIT: extension auth keys are normally disabled by Core Tools locally; this is not production key-auth verification.',flush=True)
        print('LIMIT: new bearer-route successful auth/exploration/ingress needs a configured synthetic HTTPS issuer and database fixture; direct-handler tests are separate.',flush=True)
    finally:
        if proc.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            else:proc.terminate()
        out.close();err.close()
        # Fixture has no credentials; emit bounded failure diagnostics only.
        if not success:
            for path in [folder/'host.stdout.log',folder/'host.stderr.log']:
                print(path.name+':\n'+path.read_text(errors='replace')[-12000:],flush=True)

if __name__=='__main__':main()
