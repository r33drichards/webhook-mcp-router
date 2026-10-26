"""Offline security contracts; no tokens, Azure requests or artifact downloads."""
import copy,hashlib,importlib.util,json,runpy,tempfile,zipfile
from pathlib import Path
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('deploy',root/'azure-disabled-app-deploy.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
count=0
def denied(fn):
 global count
 try:fn()
 except (ValueError,KeyError):count+=1
 else:raise AssertionError('Unsafe deployment accepted')
client='00000000-0000-0000-0000-000000000001';principal='00000000-0000-0000-0000-000000000002'
account={'id':m.SUBSCRIPTION,'tenantId':m.TENANT,'user':{'type':'servicePrincipal','name':client}}
claims={'tid':m.TENANT,'oid':principal,'appid':client,'aud':'https://management.azure.com/','exp':1000}
m.check_identity(account,claims,client,principal,100);count+=1
for key,value in [('tid','wrong'),('oid','wrong'),('appid','wrong'),('aud','wrong'),('exp',110)]:
 bad=copy.deepcopy(claims);bad[key]=value;denied(lambda:m.check_identity(account,bad,client,principal,100))
for key,value in [('id','wrong'),('tenantId','wrong'),('user',{'type':'user','name':client})]:
 bad=copy.deepcopy(account);bad[key]=value;denied(lambda:m.check_identity(bad,claims,client,principal,100))
run={'id':m.RUN,'head_sha':m.PACKAGING,'conclusion':'success','path':'.github/workflows/azure-package.yml','repository':{'full_name':m.REPO}}
artifact={'id':m.ARTIFACT,'expired':False,'digest':'sha256:'+m.WRAPPER,'name':f'router-windows-b107be25-{m.RUN}','workflow_run':{'id':m.RUN,'head_sha':m.PACKAGING}}
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
fixtures=runpy.run_path(str(root/'test-azure-disabled-app-plan-check.py'));plan=fixtures['p']
m.check_plan(plan,'create');count+=1
denied(lambda:m.check_plan(plan,'noop'))
noop=copy.deepcopy(plan);noop['resource_changes'][-1]['change']['actions']=['no-op'];m.check_plan(noop,'noop');count+=1
denied(lambda:m.check_plan(noop,'create'))
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
print(f'PASS {count} closed deployment checks; offline fixtures, no Azure identity/upload/apply performed')
