"""Exact reviewed release provenance and conditional upload; no config or identity changes."""
import hashlib,json,os,subprocess,sys,zipfile,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('azure-disabled-app-deploy.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require=base.require
command=base.command
az=base.az
ACCOUNT=base.ACCOUNT
REPO='r33drichards/webhook-mcp-router'
RUN=40477463286
ARTIFACT=12721168982
PACKAGING='8ea28a2948fce27f1f2f05c8161f0d2040220896'
APPLICATION='050e56e518269e2aa9753d6b1162a7920c404b23'
WRAPPER='400ad833b51304d3f380fc3c19a17a87628f8774116b11c051c2956f92acc2bc'
DIGEST='569149d7e4e242108c1b8d7d67de6c0f8e420f0fa1d7cf596e0cc41802ce67d8'
def check_provenance(run,artifact):
 require(run.get('id')==RUN and run.get('head_sha')==PACKAGING and run.get('conclusion')=='success' and run.get('path')=='.github/workflows/azure-package.yml')
 require(run.get('repository',{}).get('full_name')==REPO)
 require(artifact.get('id')==ARTIFACT and artifact.get('expired') is False and artifact.get('digest')=='sha256:'+WRAPPER)
 require(artifact.get('name')==f'router-windows-050e56e5-{RUN}' and artifact.get('workflow_run',{}).get('id')==RUN and artifact['workflow_run'].get('head_sha')==PACKAGING)
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
if __name__=='__main__':
 stage=sys.argv[1]
 try:
  require(stage in ('package','upload'))
  folder=Path(os.environ['ROUTER_DEPLOY_PRIVATE']);folder.mkdir(mode=0o700,exist_ok=True)
  (package if stage=='package' else upload)(folder)
  print('PASS verified router package '+stage)
 except Exception:
  raise SystemExit('FAIL OAUTH_PACKAGE_STAGE; private details withheld')
