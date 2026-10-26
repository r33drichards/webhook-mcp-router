"""Pinned package and isolated CLI checks for the closed app workflow.
No user login, credential discovery, IAM writes, key retrieval, or automatic retries.
"""
import shutil
import base64,hashlib,importlib.util,json,os,re,subprocess,sys,time,urllib.parse,urllib.request,zipfile
from pathlib import Path
REPO='r33drichards/webhook-mcp-router'
RUN=40236143640
ARTIFACT=12615790100
PACKAGING='dc2c4d51b387a1cbb4f5a86ed8bf7c823a897ab4'
APPLICATION='b107be2598d3060ccece0c99075f52dff1bb7db5'
WRAPPER='c81803336c2809952ab48a0c821f0ecb3312053244c04234fff4428d6a8d711b'
DIGEST='2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c'
TENANT='0e4545fd-804f-4acb-ad41-f955e53645c1'
SUBSCRIPTION='38d8d92f-3e84-4ef5-b3da-2788a843aa70'
SUBJECT='repo:r33drichards@57335981/webhook-mcp-router@1432792940:environment:azure-router'
ACCOUNT='whmcprv2f7076f8e38'
LOGIN_STAGE='not_started'
class CliFailed(ValueError):
 def __init__(self, stderr):
  # Only a bounded numeric provider code may escape captured CLI output.
  match=re.search(rb'\bAADSTS([0-9]{5,9})\b',stderr or b'')
  self.aadsts=match.group(1).decode('ascii') if match else None
  super().__init__('CLI_EXIT_NONZERO')
def safe_error(error):
 if isinstance(error,CliFailed):return 'CLI_EXIT_NONZERO'+(':AADSTS'+error.aadsts if error.aadsts else '')
 for cls,code in [(FileNotFoundError,'EXECUTABLE_NOT_FOUND'),(subprocess.TimeoutExpired,'PROCESS_TIMEOUT'),(KeyError,'CONFIG_MISSING'),(ValueError,'CONTRACT_OR_FORMAT'),(OSError,'OS_ERROR')]:
  if isinstance(error,cls):return code
 return 'OTHER_ERROR'

def require(ok):
 if not ok:raise ValueError('CONTRACT_MISMATCH')
def command(args):
 result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
 if result.returncode!=0:raise CliFailed(result.stderr)
 return result.stdout
def az(*args):
 executable=shutil.which('az')
 if not executable:raise FileNotFoundError('AZURE_CLI_NOT_FOUND')
 return command([executable,*args,'--only-show-errors','--output','json'])
def claims(token):
 # Local identity assertions on tokens returned over authenticated TLS; Azure
 # performs the actual GitHub signature/trust validation during exchange.
 part=token.split('.')[1];return json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
def check_identity(account,token_claims,client,principal,now):
 require(account.get('id')==SUBSCRIPTION and account.get('tenantId')==TENANT)
 require(account.get('user',{}).get('type')=='servicePrincipal' and account['user'].get('name','').lower()==client.lower())
 require(token_claims.get('tid')==TENANT and token_claims.get('oid')==principal)
 require(token_claims.get('appid',token_claims.get('azp'))==client)
 require(token_claims.get('aud') in ('https://management.azure.com/','https://management.core.windows.net/'))
 require(isinstance(token_claims.get('exp'),int) and token_claims['exp']>now+60)
def login():
 global LOGIN_STAGE
 LOGIN_STAGE='config'
 client=os.environ['ARM_CLIENT_ID'];principal=os.environ['AZURE_ROUTER_PRINCIPAL_ID']
 for value in (client,principal):require(re.fullmatch('[a-f0-9-]{36}',value) is not None)
 LOGIN_STAGE='isolated_cache'
 cache=Path(os.environ['AZURE_CONFIG_DIR']);require(not cache.exists());cache.mkdir(mode=0o700)
 require(os.environ.get('GITHUB_REPOSITORY')==REPO and os.environ.get('GITHUB_REF')=='refs/heads/main')
 LOGIN_STAGE='github_token'
 url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'];require(urllib.parse.urlsplit(url).scheme=='https')
 url+=('&' if '?' in url else '?')+urllib.parse.urlencode({'audience':'api://AzureADTokenExchange'})
 request=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
 with urllib.request.urlopen(request,timeout=30) as response:token=json.load(response)['value']
 LOGIN_STAGE='github_claims'
 c=claims(token)
 require(c.get('iss')=='https://token.actions.githubusercontent.com' and c.get('sub')==SUBJECT and c.get('aud')=='api://AzureADTokenExchange' and c.get('ref')=='refs/heads/main' and c.get('exp',0)>time.time()+60)
 LOGIN_STAGE='azure_exchange'
 az('login','--service-principal','--username',client,'--tenant',TENANT,'--federated-token',token)
 LOGIN_STAGE='subscription_select'
 az('account','set','--subscription',SUBSCRIPTION)
 LOGIN_STAGE='account_read'
 account=json.loads(az('account','show'))
 LOGIN_STAGE='arm_token'
 access=json.loads(az('account','get-access-token','--resource','https://management.azure.com/'))
 LOGIN_STAGE='azure_claims'
 check_identity(account,claims(access['accessToken']),client,principal,time.time())

def check_provenance(run,artifact):
 require(run.get('id')==RUN and run.get('head_sha')==PACKAGING and run.get('conclusion')=='success' and run.get('path')=='.github/workflows/azure-package.yml')
 require(run.get('repository',{}).get('full_name')==REPO)
 require(artifact.get('id')==ARTIFACT and artifact.get('expired') is False and artifact.get('digest')=='sha256:'+WRAPPER)
 require(artifact.get('name')==f'router-windows-b107be25-{RUN}' and artifact.get('workflow_run',{}).get('id')==RUN and artifact['workflow_run'].get('head_sha')==PACKAGING)
def unpack(archive,destination,wrapper=WRAPPER,digest=DIGEST):
 require(0<archive.stat().st_size<=100_000_000 and hashlib.sha256(archive.read_bytes()).hexdigest()==wrapper)
 with zipfile.ZipFile(archive) as z:
  require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())=={'router.zip','SHA256SUMS','build.json','files.json'})
  require(z.getinfo('router.zip').file_size<=262144000 and z.getinfo('build.json').file_size<=4096)
  build=json.loads(z.read('build.json').decode('utf-8-sig'))
  require(build.get('applicationCommit')==APPLICATION and build.get('packagingCommit')==PACKAGING and str(build.get('runId'))==str(RUN) and build.get('zipSha256')==digest)
  data=z.read('router.zip');require(hashlib.sha256(data).hexdigest()==digest)
  destination.write_bytes(data)
def package(folder):
 run=json.loads(command(['gh','api',f'repos/{REPO}/actions/runs/{RUN}']))
 artifact=json.loads(command(['gh','api',f'repos/{REPO}/actions/artifacts/{ARTIFACT}']))
 check_provenance(run,artifact)
 archive=folder/'artifact.zip'
 with archive.open('wb') as output:
  result=subprocess.run(['gh','api',f'repos/{REPO}/actions/artifacts/{ARTIFACT}/zip'],stdout=output,stderr=subprocess.PIPE,timeout=180)
 require(result.returncode==0)
 unpack(archive,folder/'router.zip')
def upload(folder):
 package_path=folder/'router.zip';require(hashlib.sha256(package_path.read_bytes()).hexdigest()==DIGEST)
 args=['--account-name',ACCOUNT,'--container-name','router-packages','--name',DIGEST+'.zip','--auth-mode','login']
 az('storage','blob','upload',*args,'--file',str(package_path),'--type','block','--overwrite','false','--if-none-match','*')
 downloaded=folder/'downloaded.zip'
 az('storage','blob','download',*args,'--file',str(downloaded),'--no-progress')
 require(downloaded.stat().st_size==package_path.stat().st_size and hashlib.sha256(downloaded.read_bytes()).hexdigest()==DIGEST)
def check_plan(plan,mode):
 spec=importlib.util.spec_from_file_location('closed',Path(__file__).with_name('azure-disabled-app-plan-check.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.validate(plan,DIGEST)
 app=next(row for row in plan['resource_changes'] if row['address']=='azapi_resource.app[0]')
 require(app['change']['actions']==(['create'] if mode=='create' else ['no-op']))
 if mode=='create':require(app['change'].get('before') is None)
if __name__=='__main__':
 stage=sys.argv[1]
 try:
  if stage=='login':login()
  elif stage in ('package','upload'):
   folder=Path(os.environ['ROUTER_DEPLOY_PRIVATE']);folder.mkdir(mode=0o700,exist_ok=True)
   (package if stage=='package' else upload)(folder)
  elif stage in ('create','noop'):check_plan(json.loads(Path(sys.argv[2]).read_text()),stage)
  else:raise ValueError('UNKNOWN_STAGE')
  print('PASS closed deployment stage '+stage)
 except Exception as error:
  # Neither subprocess error output nor exception values may disclose tokens,
  # signed artifact URLs, private plan fields, or runtime configuration.
  if stage=='login':print('LOGIN_DIAGNOSTIC stage='+LOGIN_STAGE+' category='+safe_error(error),file=sys.stderr)
  raise SystemExit('FAIL closed deployment stage '+(stage if stage in ('login','package','upload','create','noop') else 'invalid')+'; private details withheld')
