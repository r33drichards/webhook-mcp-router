"""Pinned official WCGI example: synthetic guest/hosted assertions, no service secrets."""
import importlib.util,json,os,pathlib,subprocess,sys,time,urllib.error,urllib.request
spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)

def guest(wasm):
    for body in ('','Synthetic'):
        env={'REQUEST_METHOD':'POST','SERVER_PROTOCOL':'HTTP/1.1','SERVER_NAME':'localhost','SERVER_PORT':'80',
             'GATEWAY_INTERFACE':'CGI/1.1','SCRIPT_NAME':'rust_wcgi','REQUEST_URI':'/',
             'CONTENT_TYPE':'text/plain','CONTENT_LENGTH':str(len(body))}
        cmd=['wasmer','run',str(pathlib.Path(wasm).resolve())]
        for name,value in env.items():cmd+=['--env',name+'='+value]
        r=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=60)
        assert r.returncode==0,'official guest failed'
        headers,payload=r.stdout.split('\n\n',1)
        assert payload=='Hello, '+(body or 'World')+'!','official guest body mismatch'
        assert 'content-type:' in headers.lower(),'missing CGI headers'
        print(json.dumps({'stage':'official-guest','exit_code':r.returncode,'synthetic_response_verified':True}))
    # Reproduce the exact hosted panic with one missing CGI metadata key.
    # All values remain synthetic; never enumerate the process environment.
    missing=dict(env);missing.pop('REQUEST_METHOD')
    cmd=['wasmer','run',str(pathlib.Path(wasm).resolve())]
    for name,value in missing.items():cmd+=['--env',name+'='+value]
    r=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=60)
    assert r.returncode!=0 and 'lib.rs:259:30' in r.stderr and 'no entry found for key' in r.stderr, 'missing-method panic reproduction mismatch'
    print(json.dumps({'stage':'missing-CGI-metadata-negative','missing_key':'REQUEST_METHOD',
                      'exit_code':r.returncode,'exact_hosted_panic_reproduced':True}))

def hosted():
    if any(os.environ.get(n) for n in edge.NAMES) or edge.secret_names():raise RuntimeError('service secrets must be absent')
    sha=os.environ['GITHUB_SHA']
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise RuntimeError('invalid source revision')
    p=pathlib.Path('deploy/wasmer.toml');p.write_text(p.read_text().replace('version = "0.0.1"','version = "0.0.1-ci.'+sha[:12]+'.official"',1))
    edge.cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    if edge.secret_names():raise RuntimeError('unexpected service-secret names')
    for body in (None,b'Synthetic'):
        expected=b'Hello, World!' if body is None else b'Hello, Synthetic!'
        for attempt in range(8):
            req=urllib.request.Request('https://webhook-mcp-router.wasmer.app/',data=body,headers={'Content-Type':'text/plain','Accept':'text/plain'})
            try:r=edge.OPENER.open(req,timeout=20)
            except urllib.error.HTTPError as error:r=error
            with r:status=r.status;data=r.read(65537)
            matched=status==200 and data==expected
            print(json.dumps({'stage':'official-hosted','method':'GET' if body is None else 'POST',
                              'attempt':attempt+1,'status':status,'bytes_read':len(data),'expected_body':matched}),flush=True)
            if matched:break
            time.sleep(5)
        else:raise RuntimeError('official hosted response failed')
    if edge.secret_names():raise RuntimeError('service-secret absence unverified')
    print('PASS official WCGI hosted GET/POST synthetic replies; no service secrets')

if __name__=='__main__':
    try:
        if sys.argv[1]=='guest':guest(sys.argv[2])
        elif sys.argv[1]=='hosted':hosted()
        else:raise RuntimeError('invalid mode')
    except Exception:
        print('FAIL official WCGI reproduction; no service secrets created',flush=True)
        raise SystemExit(1)
