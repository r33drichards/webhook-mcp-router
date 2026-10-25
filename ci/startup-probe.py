"""Credential-free packaged CGI diagnostic; never creates service secrets."""
import importlib.util,json,os,pathlib,sys,time,urllib.error,urllib.request
spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)

def request(url):
    try:response=edge.OPENER.open(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=20)
    except urllib.error.HTTPError as error:response=error
    with response:
        body=response.read(65537);status=response.status
    # Fixed-code-only evidence; no arbitrary platform response text.
    data=None
    try:data=json.loads(body)
    except (ValueError,UnicodeError):pass
    allowed={'POC_DIAGNOSTIC_ONLY','POC_SIGNING_CONFIG_INVALID','POC_ACCESS_CONFIG_INVALID','POC_STORAGE_CONFIG_INVALID',
             'POC_CALLBACK_CONFIG_INVALID','POC_WINDOW_EXPIRED','POC_HTTP_CLIENT_INIT_FAILED',
             'POC_STORAGE_INIT_FAILED','POC_STARTUP_FAILED','POC_CGI_SERVE_FAILED'}
    code=data.get('error') if isinstance(data,dict) else None
    ready=isinstance(data,dict) and data=={'status':'runtime-ready'}
    return {'status':status,'bytes_read':len(body),'truncated':len(body)>65536,
            'runtime_ready':ready,'startup_code':code if isinstance(code,str) and code in allowed else None}

def main():
    constant=len(sys.argv)>1 and sys.argv[1]=='constant'
    if any(os.environ.get(n) for n in edge.NAMES):raise RuntimeError('service secrets must not be supplied')
    if edge.secret_names():raise RuntimeError('app must have no approved service-secret names')
    sha=os.environ['GITHUB_SHA']
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise RuntimeError('invalid revision')
    p=pathlib.Path('deploy/wasmer.toml');p.write_text(p.read_text().replace('version = "0.0.1"','version = "0.0.1-ci.'+sha[:12]+('.constant' if constant else '')+'"',1))
    edge.cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    # Canonical endpoint only; no redirects or arbitrary callbacks.
    if edge.secret_names():raise RuntimeError('unexpected service-secret names')
    base='https://webhook-mcp-router.wasmer.app'
    for attempt in range(8):
        health=request(base+'/_poc/health')
        print(json.dumps({'path':'/_poc/health','attempt':attempt+1,**health}),flush=True)
        if health['status']==200 and health['runtime_ready']:break
        time.sleep(5)
    else:raise RuntimeError('packaged CGI health failed')
    mcp=request(base+'/mcp');print(json.dumps({'path':'/mcp',**mcp}),flush=True)
    if mcp['status']!=(404 if constant else 503) or mcp['startup_code']!=('POC_DIAGNOSTIC_ONLY' if constant else 'POC_SIGNING_CONFIG_INVALID'):raise RuntimeError('unexpected credential-free startup result')
    if edge.secret_names():raise RuntimeError('service-secret absence not confirmed')
    print('PASS hosted packaged CGI health; fixed nonfunctional route response; service secrets absent')

if __name__=='__main__':
    try:main()
    except Exception:
        print('FAIL credential-free startup probe; no service secrets created',flush=True)
        raise SystemExit(1)
