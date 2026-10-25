"""Approved isolated Wasmer POC lifecycle. Never prints CLI bodies or secrets.

Wasmer published schema replaces deprecated secret APIs with envVars/updateEnvVars.
Approved values travel only in TLS API bodies with sensitive=true, never logs/files.
GitHub environment-secret deletion requires the coordinating browser owner.
"""
import datetime,json,os,pathlib,re,socket,ssl,subprocess,sys,time,urllib.error,urllib.parse,urllib.request

APP='r33drichards/webhook-mcp-router'
APP_ID='da_K6AIot5U1ND7'
API='https://registry.wasmer.io/graphql'
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

def graphql(query,variables):
    request=urllib.request.Request(API,data=json.dumps({'query':query,'variables':variables}).encode(),headers={'Authorization':'Bearer '+os.environ['WASMER_TOKEN'],'Content-Type':'application/json'})
    with OPENER.open(request,timeout=45) as response:
        body=response.read(262145)
        if len(body)>262144:raise RuntimeError('API response limit')
        data=json.loads(body)
    if data.get('errors') or not isinstance(data.get('data'),dict):raise RuntimeError('API rejected operation; response withheld')
    return data['data']

ENV_QUERY="""query POCEnvMetadata($owner:String!,$name:String!,$names:[String]) {
 getDeployApp(owner:$owner,name:$name) {
  id name url envVars(names:$names,first:10) {edges {node {name sensitive}} pageInfo {hasNextPage}}
 }
}"""
UPDATE_QUERY="""mutation POCEnvUpdate($input:UpdateEnvVarsInput!) {updateEnvVars(input:$input) {success}}"""

def secret_metadata():
    app=graphql(ENV_QUERY,{'owner':'r33drichards','name':'webhook-mcp-router','names':list(NAMES)}).get('getDeployApp')
    if not app or app.get('id')!=APP_ID or app.get('name')!='webhook-mcp-router':raise RuntimeError('canonical app identity mismatch')
    connection=app.get('envVars')
    if not isinstance(connection,dict) or connection.get('pageInfo',{}).get('hasNextPage') is not False:raise RuntimeError('incomplete environment metadata')
    nodes=[edge['node'] for edge in connection['edges']]
    names={item['name']:item['sensitive'] for item in nodes}
    if set(names)-set(NAMES) or len(names)!=len(nodes):raise RuntimeError('unexpected environment metadata')
    return names

def secret_names():return set(secret_metadata())

def update_env(updates):
    if not updates or any(item.get('name') not in NAMES for item in updates):raise RuntimeError('unapproved secret name')
    if any(not item.get('delete') and item.get('sensitive') is not True for item in updates):raise RuntimeError('secret must be sensitive')
    # Re-verify owner/name/ID before any mutation, including cleanup.
    secret_metadata()
    result=graphql(UPDATE_QUERY,{'input':{'appId':APP_ID,'envVars':updates}}).get('updateEnvVars')
    if not result or result.get('success') is not True:raise RuntimeError('environment update not confirmed')

def save(state):
    STATE.write_text(json.dumps(state)) # app identifiers/status only; never values

def inspect_secrets():
    print(json.dumps({'operation':'current envVars metadata only','app_id':APP_ID,'names_and_sensitivity':secret_metadata()}),flush=True)

# Deliberately emit no free-form response text: an error page may echo request
# credentials. These fixed phrases retain useful platform diagnostics safely.
BODY_MARKERS=('bad gateway','service unavailable','internal server error',
              'unauthorized','forbidden','application error','runtime error',
              'synthetic CGI configuration or execution failed',
              'method not allowed','not found')

def readiness_probe(request):
    diagnostic={'category':'unknown','status':None}
    try:
        try:
            response=OPENER.open(request,timeout=15)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            diagnostic['status']=response.status
            body=response.read(65537)
        text=body.decode('utf-8',errors='replace')
        diagnostic['body']={'bytes_read':len(body),'truncated':len(body)>65536,
                            'recognized_errors':[p for p in BODY_MARKERS if p.lower() in text.lower()]}
        if len(body)>65536:
            diagnostic['category']='response_limit';return False,diagnostic
        try:
            value=json.loads(body)
            diagnostic['body']['format']='json'
        except (ValueError,UnicodeError):
            diagnostic['body']['format']='non_json'
            diagnostic['category']='invalid_json' if response.status==200 else 'http_error'
            return False,diagnostic
        if response.status!=200:diagnostic['category']='http_error'
        elif not isinstance(value,dict) or not isinstance(value.get('result'),dict):
            diagnostic['category']='rpc_error' if isinstance(value,dict) and 'error' in value else 'missing_result'
        else:
            diagnostic['category']='ready';return True,diagnostic
    except Exception as error:
        reason=error.reason if isinstance(error,urllib.error.URLError) else error
        if isinstance(reason,ssl.SSLError):diagnostic['category']='tls_error'
        elif isinstance(reason,(TimeoutError,socket.timeout)):diagnostic['category']='timeout'
        elif isinstance(reason,socket.gaierror):diagnostic['category']='dns_error'
        elif isinstance(error,urllib.error.URLError):diagnostic['category']='connection_error'
        else:diagnostic['category']='request_error'
    return False,diagnostic

def deploy():
    global stage
    for name in (*NAMES,'WASMER_TOKEN'):
        if not os.environ.get(name):raise RuntimeError('missing approved environment secret')
    state={'secrets_attempted':False,'app':APP}
    save(state)
    stage='validate-canonical-app-and-empty-approved-names'
    if secret_names():raise RuntimeError('temporary names already exist; refuse overwrite')
    stage='bootstrap-fail-closed-app'
    manifest=pathlib.Path('deploy/wasmer.toml')
    sha=os.environ.get('GITHUB_SHA','')
    if sha:
        if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise RuntimeError('invalid source revision')
        manifest.write_text(manifest.read_text().replace('version = "0.0.1"','version = "0.0.1-ci.'+sha[:12]+'"',1))
    # Startup has no service credentials yet and fails closed. No health wait.
    cli('deploy','--dir','deploy','--non-interactive','--publish-package','--no-persist-id','--no-wait','--format=json')
    app=json.loads(cli('app','get',APP,'--format=json'))
    if app.get('id')!=APP_ID:raise RuntimeError('deployed app identity mismatch')
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
    stage='inspect-secret-names-before-create'
    if secret_names().intersection(NAMES):raise RuntimeError('temporary names already exist; refuse overwrite')
    stage='transfer-approved-app-secrets'
    state['secrets_attempted']=True;save(state)
    update_env([{'name':name,'value':os.environ[name],'sensitive':True} for name in NAMES])
    if secret_metadata()!={name:True for name in NAMES}:raise RuntimeError('sensitive secret creation not confirmed')
    stage='redeploy-sensitive-environment'
    redeployed=graphql('mutation POCRedeploy($id:ID!) {redeployActiveAppVersion(input:{appId:$id}) {app {id}}}',{'id':APP_ID}).get('redeployActiveAppVersion')
    if not redeployed or redeployed.get('app',{}).get('id')!=APP_ID:raise RuntimeError('redeploy not confirmed')
    print('Confirmed three temporary app-secret names; values withheld',flush=True)
    stage='wait-for-initialized-service'
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'synthetic-ready','version':'1'}}}).encode()
    for attempt in range(24):
        request=urllib.request.Request(url+'/mcp',data=body,headers={'Authorization':'Bearer '+os.environ['POC_TEST_TOKEN'],'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'})
        ready,diagnostic=readiness_probe(request)
        if ready:break
        print(json.dumps({'stage':stage,'attempt':attempt+1,**diagnostic}),flush=True)
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
        try:update_env([{'name':name,'delete':True}])
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
    if errors:
        print('Cleanup residual checks: '+', '.join(errors),flush=True)
        raise RuntimeError('Wasmer cleanup incomplete')
    print('PASS verified removal of three Wasmer secret names, credential-free redeploy and live rejection',flush=True)
    print('PENDING browser verification: delete only three POC secrets from GitHub wasmer-poc environment; leave WASMER_TOKEN unchanged',flush=True)

if __name__=='__main__':
    try:
        {'deploy':deploy,'cleanup':cleanup,'inspect':inspect_secrets}[sys.argv[1]]()
    except Exception:
        print('FAIL isolated Edge lifecycle stage='+stage+'; details withheld',file=sys.stderr)
        sys.exit(1)
