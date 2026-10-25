"""One credential-free deployment to observe CGI envelope, no functional service."""
import importlib.util,json,os,pathlib,time,urllib.error,urllib.request
spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)
def main():
    if any(os.environ.get(n) for n in edge.NAMES) or edge.secret_names():raise RuntimeError('service credentials must be absent')
    sha=os.environ['GITHUB_SHA']
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise RuntimeError('invalid source revision')
    p=pathlib.Path('deploy/wasmer.toml');p.write_text(p.read_text().replace('version = "0.0.1"','version = "0.0.1-ci.'+sha[:12]+'.envelope"',1))
    edge.cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    if edge.secret_names():raise RuntimeError('unexpected service-secret names')
    fields=('request_method_present','method_is_get','method_is_post','script_name_present','server_protocol_present',
            'gateway_interface_present','content_length_present','stdin_read_ok','stdin_empty','stdin_synthetic')
    healthy=True
    # Both methods are attempted even when GET fails, to distinguish handling.
    for body in (None,b'Synthetic'):
        method='GET' if body is None else 'POST'
        for attempt in range(3):
            req=urllib.request.Request('https://webhook-mcp-router.wasmer.app/',data=body,headers={'Content-Type':'text/plain','Accept':'application/json'})
            try:r=edge.OPENER.open(req,timeout=20)
            except urllib.error.HTTPError as error:r=error
            with r:status=r.status;raw=r.read(65537)
            report={}
            try:
                data=json.loads(raw)
                report={k:data[k] for k in fields if isinstance(data.get(k),bool)}
            except (ValueError,AttributeError):pass
            print(json.dumps({'method':method,'attempt':attempt+1,'status':status,'bytes_read':len(raw),'report':report}),flush=True)
            if status==200 and len(report)==len(fields):break
            time.sleep(5)
        valid=status==200 and len(report)==len(fields) and report['request_method_present'] and report['stdin_read_ok']
        valid=valid and report['method_is_get']==(method=='GET') and report['method_is_post']==(method=='POST')
        valid=valid and (report['stdin_empty'] if body is None else report['stdin_synthetic'])
        healthy=healthy and valid
    if edge.secret_names():raise RuntimeError('service-secret absence unverified')
    if not healthy:raise RuntimeError('hosted CGI envelope mismatch; inspect fixed CGI_ENVELOPE_PROBE runtime markers')
    print('PASS hosted per-request GET/POST CGI metadata and synthetic stdin')
if __name__=='__main__':
    try:main()
    except Exception:
        print('FAIL CGI envelope diagnostic; no service credentials created',flush=True)
        raise SystemExit(1)
