"""Approved isolated Wasmer POC lifecycle. Never prints CLI bodies or secrets.

CLI 7.5.0 source, not its misleading JSON help text, confirms secret --from-file
reads dotenv. Values flow through stdin, never argv, package files or artifacts.
GitHub environment-secret deletion requires the coordinating browser owner.
"""
import datetime,json,os,pathlib,subprocess,sys,time,urllib.error,urllib.parse,urllib.request

APP='r33drichards/webhook-mcp-router'
NAMES=('POC_TEST_TOKEN','POC_RECEIPT_TOKEN','POC_WEBHOOK_SECRET')
STATE=pathlib.Path(os.environ.get('RUNNER_TEMP','/tmp'))/'webhook-edge-state.json'
stage='configuration'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('redirect refused')
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)


def cli(*args,stdin=None):
    result=subprocess.run(['wasmer',*args],input=stdin,text=True,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError('Wasmer command failed; private output withheld')
    return result.stdout

def secret_names():
    result=json.loads(cli('app','secret','list','--app',APP,'--format=json','--non-interactive'))
    if not isinstance(result,list):raise RuntimeError('unexpected secret-list shape')
    return {item['name'] for item in result}

def save(state):
    STATE.write_text(json.dumps(state)) # app identifiers/status only; never values

def deploy():
    global stage
    for name in (*NAMES,'WASMER_TOKEN'):
        if not os.environ.get(name):raise RuntimeError('missing approved environment secret')
    state={'secrets_attempted':False,'app':APP}
    save(state)
    stage='bootstrap-fail-closed-app'
    manifest=pathlib.Path('deploy/wasmer.toml')
    sha=os.environ.get('GITHUB_SHA','')
    if sha:
        if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise RuntimeError('invalid source revision')
        manifest.write_text(manifest.read_text().replace('version = "0.0.1"','version = "0.0.1-ci.'+sha[:12]+'"',1))
    # Startup has no service credentials yet and fails closed. No health wait.
    cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    app=json.loads(cli('app','get',APP,'--format=json'))
    url=app['url'].rstrip('/')
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.wasmer.app') or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError('unexpected owned app endpoint')
    state['url']=url;save(state)
    print('Verified dedicated app endpoint: '+url,flush=True)
    stage='configure-owned-callback-and-expiration'
    config=pathlib.Path('deploy/app.yaml')
    # JSON quoted scalars are valid YAML, and these are nonsecret settings.
    expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    text=config.read_text()
    text=text.replace('env:\n','env:\n  POC_CALLBACK_URL: '+json.dumps(url+'/callback')+'\n  POC_EXPIRES_AT: '+json.dumps(expiry)+'\n  POC_DNS_SERVER: '+json.dumps(os.environ['POC_DNS_SERVER'])+'\n',1)
    config.write_text(text)
    state['expires_at']=expiry;save(state)
    cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    stage='create-only-approved-app-secrets'
    if secret_names().intersection(NAMES):raise RuntimeError('temporary names already exist; refuse overwrite')
    state['secrets_attempted']=True;save(state)
    dotenv=''.join(name+'='+os.environ[name]+'\n' for name in NAMES)
    cli('app','secret','create','--app',APP,'--from-file','/dev/stdin','--non-interactive','--redeploy',stdin=dotenv)
    if not set(NAMES)<=secret_names():raise RuntimeError('secret creation not confirmed')
    print('Confirmed three temporary app-secret names; values withheld',flush=True)
    stage='wait-for-initialized-service'
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'synthetic-ready','version':'1'}}}).encode()
    for attempt in range(24):
        request=urllib.request.Request(url+'/mcp',data=body,headers={'Authorization':'Bearer '+os.environ['POC_TEST_TOKEN'],'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'})
        try:
            with OPENER.open(request,timeout=15) as response:
                value=json.loads(response.read(65536))
                if response.status==200 and 'result' in value:break
        except Exception:pass
        time.sleep(5)
    else:raise RuntimeError('hosted initialization unavailable')
    # Public endpoint outputs only; credentials stay step-scoped environment values.
    with open(os.environ['GITHUB_ENV'],'a') as out:
        for name,path in [('POC_MCP_URL','/mcp'),('POC_RECEIPTS_URL','/receipts'),('POC_CALLBACK_URL','/callback')]:out.write(name+'='+url+path+'\n')
    print('PASS hosted initialization; starting full synthetic lifecycle',flush=True)

def cleanup():
    global stage
    if not STATE.exists():print('No Wasmer lifecycle writes recorded');return
    state=json.loads(STATE.read_text())
    if not state.get('secrets_attempted'):print('No service-secret creation attempted');return
    errors=[]
    for name in NAMES:
        stage='delete-'+name
        try:cli('app','secret','delete','--app',APP,'--force','--non-interactive',name)
        except Exception:errors.append(name)
    stage='verify-secret-removal'
    try:
        if secret_names().intersection(NAMES):errors.append('remaining names')
    except Exception:errors.append('verification unavailable')
    stage='redeploy-without-service-secrets'
    try:cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    except Exception:errors.append('credential-free redeploy')
    stage='verify-live-rejection'
    if state.get('url'):
        for attempt in range(18):
            request=urllib.request.Request(state['url']+'/mcp',data=b'{}',headers={'Authorization':'Bearer '+os.environ.get('POC_TEST_TOKEN',''),'Content-Type':'application/json'})
            try:
                with OPENER.open(request,timeout=10) as response:status=response.status
            except urllib.error.HTTPError as error:status=error.code
            except Exception:status=0
            if status in (401,500,502,503):break
            time.sleep(5)
        else:errors.append('old credential rejection unverified')
    # Earlier app versions also carry a one-hour service expiration safeguard.
    if errors:raise RuntimeError('Wasmer cleanup incomplete')
    print('PASS verified removal of three Wasmer secret names, credential-free redeploy and live rejection',flush=True)
    print('PENDING browser verification: delete only three POC secrets from GitHub wasmer-poc environment; leave WASMER_TOKEN unchanged',flush=True)

if __name__=='__main__':
    try:
        {'deploy':deploy,'cleanup':cleanup}[sys.argv[1]]()
    except Exception:
        print('FAIL isolated Edge lifecycle stage='+stage+'; details withheld',file=sys.stderr)
        sys.exit(1)
