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
RUN=40483488868
ARTIFACT=12724002205
PACKAGING='5cea16c3d4e77bcaeb1b11f6a812006daf17f354'
APPLICATION='71085060f001b3f2d20a2d96941a1377286a4fb0'
WRAPPER='67c03de851012f97f19273b7e47e64a27a414107f9efa81e13ba59d1a5a7e46b'
DIGEST='4375b7c0546a524339a0698d0e86fb23727c7af3c7d1c257b45fe19a95d9ef35'
def check_provenance(run,artifact):
 require(run.get('id')==RUN and run.get('head_sha')==PACKAGING and run.get('conclusion')=='success' and run.get('path')=='.github/workflows/azure-package.yml')
 require(run.get('repository',{}).get('full_name')==REPO)
 require(artifact.get('id')==ARTIFACT and artifact.get('expired') is False and artifact.get('digest')=='sha256:'+WRAPPER)
 require(artifact.get('name')==f'router-windows-71085060-{RUN}' and artifact.get('workflow_run',{}).get('id')==RUN and artifact['workflow_run'].get('head_sha')==PACKAGING)
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
