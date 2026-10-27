"""Offline security contracts; no tokens, Azure requests or artifact downloads."""
import copy,hashlib,importlib.util,json,runpy,tempfile,zipfile
from pathlib import Path
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('deploy',root/'azure-oauth-package-deploy.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
count=0
def denied(fn):
 global count
 try:fn()
 except (ValueError,KeyError):count+=1
 else:raise AssertionError('Unsafe deployment accepted')
run={'id':m.RUN,'head_sha':m.PACKAGING,'conclusion':'success','path':'.github/workflows/azure-package.yml','repository':{'full_name':m.REPO}}
artifact={'id':m.ARTIFACT,'expired':False,'digest':'sha256:'+m.WRAPPER,'name':f'router-windows-2ab67cb0-{m.RUN}','workflow_run':{'id':m.RUN,'head_sha':m.PACKAGING}}
m.check_provenance(run,artifact);count+=1
for key,value in [('id',1),('expired',True),('digest','wrong'),('name','wrong'),('workflow_run',{'id':2,'head_sha':m.PACKAGING})]:
 bad=copy.deepcopy(artifact);bad[key]=value;denied(lambda:m.check_provenance(run,bad))
for key,value in [('head_sha','wrong'),('conclusion','failure'),('repository',{'full_name':'other/repo'}),('path','other.yml')]:
 bad=copy.deepcopy(run);bad[key]=value;denied(lambda:m.check_provenance(bad,artifact))
with tempfile.TemporaryDirectory() as tmp:
 folder=Path(tmp);archive=folder/'artifact.zip';dest=folder/'router.zip';data=b'synthetic package';digest=hashlib.sha256(data).hexdigest()
 build={'applicationCommit':m.APPLICATION,'packagingCommit':m.PACKAGING,'runId':str(m.RUN),'zipSha256':digest}
 def fixture(extra=None):
  with zipfile.ZipFile(archive,'w') as z:
   for name,content in [('router.zip',data),('build.json',json.dumps(build)),('files.json','[]'),('SHA256SUMS','fixture')]:z.writestr(name,content)
   if extra:z.writestr(extra,b'not extracted')
  return hashlib.sha256(archive.read_bytes()).hexdigest()
 wrapper=fixture();m.unpack(archive,dest,wrapper,digest);assert dest.read_bytes()==data;count+=1
 denied(lambda:m.unpack(archive,dest,'0'*64,digest))
 denied(lambda:m.unpack(archive,dest,wrapper,'0'*64))
 wrapper=fixture('../escape');denied(lambda:m.unpack(archive,dest,wrapper,digest))
 build['applicationCommit']='wrong';wrapper=fixture();denied(lambda:m.unpack(archive,dest,wrapper,digest))
# Prove CLI upload is conditional and every data call uses explicit Entra auth.
with tempfile.TemporaryDirectory() as tmp:
 folder=Path(tmp);data=b'synthetic package';(folder/'router.zip').write_bytes(data);old=m.DIGEST;m.DIGEST=hashlib.sha256(data).hexdigest();calls=[]
 def fake_az(*args):
  calls.append(args)
  if args[:3]==('storage','blob','download'):(folder/'downloaded.zip').write_bytes(data)
  return b'{}'
 m.az=fake_az;m.upload(folder)
 assert calls[0][-6:]==('--type','block','--overwrite','false','--if-none-match','*')
 assert all(args[args.index('--auth-mode')+1]=='login' for args in calls);count+=1
 def broken_download(*args):
  if args[:3]==('storage','blob','download'):(folder/'downloaded.zip').write_bytes(b'corrupt')
 m.az=broken_download;denied(lambda:m.upload(folder));m.DIGEST=old
print(f'PASS {count} OAuth release provenance/upload checks; offline fixtures, no Azure identity/upload/apply performed')

w=(root.parent/'.github/workflows/azure-router-oauth-package.yml').read_text()
for required in ("environment: azure-router", "github.ref == 'refs/heads/main'", "actions: read", "id-token: write", "TF_VAR_sql_outbound_ips: '[]'", "TF_VAR_dispatch_enabled: 'false'", "TF_VAR_public_mcp_ingress: 'true'", 'test "$GITHUB_SHA" = "$REVIEWED_COMMIT"', 'python3 ci/azure-disabled-app-deploy.py login', 'python3 ci/azure-oauth-package-deploy.py package', 'python3 ci/azure-oauth-package-deploy.py upload', 'python ../../../ci/azure-package-update-plan-check.py "$RUNNER_TEMP/router-post.json" --require-noop', 'if: always()'):assert required in w,required
for forbidden in ('secrets.', 'az keyvault', 'az role assignment', 'actions: write'):assert forbidden not in w,forbidden
assert w.index('router-plan.sha256') < w.index('azure-oauth-package-deploy.py upload') < w.index('terraform apply')
assert m.DIGEST in w
print('PASS package workflow isolation, plan/upload/apply ordering and cleanup')
