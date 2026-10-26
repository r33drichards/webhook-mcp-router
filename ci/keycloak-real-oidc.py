import os,json,ssl,time,secrets,subprocess,urllib.request,urllib.parse,urllib.error,shutil,hashlib,base64,http.cookiejar,html,re,socket
from pathlib import Path

expected_ref='refs/heads/ci/keycloak-real-oidc-qualification'
if os.environ.get('GITHUB_REPOSITORY')!='r33drichards/webhook-mcp-router' or os.environ.get('GITHUB_REF')!=expected_ref:
 raise SystemExit('UNAPPROVED_WORKFLOW_CONTEXT')

try:
 from pathlib import Path
 P=Path(os.environ['RUNNER_TEMP'])/'router-real-oidc';P.mkdir(mode=0o700,exist_ok=False); BASE='https://localhost:18444'; NAME='router-federation-probe'; NET='router-federation-isolated'; results=[]; durations={}
 def cmd(args):return subprocess.run(args,capture_output=True,text=True,check=True).stdout.strip()
 def ck(n,v):
  results.append({'test':n,'passed':bool(v)});print(('PASS ' if v else 'FAIL ')+n,flush=True);(P/'results.json').write_text(json.dumps(results,indent=2))
  if not v:raise RuntimeError(n)
 target_ip=None
 original_connect=socket.create_connection
 def connect(address,*args,**kwargs):
  if address==('localhost',18444):address=(target_ip,8443)
  return original_connect(address,*args,**kwargs)
 socket.create_connection=connect
 admin=secrets.token_urlsafe(32)
 (P/'env').write_text('KC_BOOTSTRAP_ADMIN_USERNAME=synthetic-admin\nKC_BOOTSTRAP_ADMIN_PASSWORD='+admin+'\n');os.chmod(P/'env',0o600)
 cmd(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(P/'server.key'),'-out',str(P/'server.crt'),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'])
 os.chmod(P/'server.key',0o644);ctx=ssl.create_default_context(cafile=str(P/'server.crt'))
 cmd(['docker','network','create',NET]);ck('private test network exists',bool(cmd(['docker','network','inspect',NET])))
 def req(path,method='GET',data=None,token=None,form=False):
  h={}
  if token:h['Authorization']='Bearer '+token
  if data is not None:h['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json';data=(urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
  try:
   with urllib.request.urlopen(urllib.request.Request(BASE+path,data=data,headers=h,method=method),context=ctx,timeout=10) as r:
    b=r.read();return r.status,json.loads(b) if b else None
  except urllib.error.HTTPError as e:return e.code,None
 images={'26.8.1':'quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b'}
 (P/'images.json').write_text(json.dumps(images))
 def start(v,data,label):
  global target_ip
  data.mkdir(exist_ok=True)
  # Restore copies retain original uid and are writable only inside private fixture.
  # Synthetic fixture only: uid0 in container, never privileged; cleanup removes generated data.
  t=time.monotonic()
  cmd(['docker','run','-d','--name',NAME,'--user','0:0','--network',NET,'--memory=4g','--cpus=2','--env-file',str(P/'env'),'-v',str(P/'server.crt')+':/tls/server.crt:ro','-v',str(P/'server.key')+':/tls/server.key:ro','-v',str(data)+':/opt/keycloak/data',images[v],'start-dev','--http-enabled=false','--https-certificate-file=/tls/server.crt','--https-certificate-key-file=/tls/server.key','--hostname='+BASE])
  target_ip=json.loads(cmd(['docker','inspect',NAME]))[0]['NetworkSettings']['Networks'][NET]['IPAddress']
  for _ in range(150):
   try:
    if req('/realms/master/.well-known/openid-configuration')[0]==200:break
   except Exception:pass
   time.sleep(1)
  else:
   raise RuntimeError(label+' startup timeout')
  durations[label]=round(time.monotonic()-t,2);ck(label+' HTTPS ready',True)
 def stop(label):
  # Data cleanup runs in a bounded helper container; no permission broadening needed.
  t=time.monotonic();cmd(['docker','stop','--timeout','30',NAME]);d=json.loads(cmd(['docker','inspect',NAME]))[0]
  logs=cmd(['docker','logs',NAME])
  ck(label+' graceful stop',not d['State']['Running'] and d['State']['ExitCode'] in (0,143) and not d['State']['OOMKilled'] and 'Keycloak stopped in' in logs)
  cmd(['docker','rm',NAME]);durations[label+'-stop']=round(time.monotonic()-t,2)
 def master():
  s,d=req('/realms/master/protocol/openid-connect/token','POST',{'grant_type':'password','client_id':'admin-cli','username':'synthetic-admin','password':admin},form=True);ck('bootstrap auth succeeds',s==200);return d['access_token']
 import threading,select,socketserver
 start('26.8.1',P/'data','federation')
 # Runner fixture permits outbound HTTPS for actual GitHub JWKS; no no-egress claim.
 a=master();realm='webhook-router';issuer='https://token.actions.githubusercontent.com';subject='repo:r33drichards@57335981/webhook-mcp-router@1432792940:ref:refs/heads/ci/keycloak-real-oidc-qualification';aud=BASE+'/realms/'+realm
 ck('create synthetic router realm',req('/admin/realms','POST',{'realm':realm,'enabled':True,'sslRequired':'all','accessTokenLifespan':90},a)[0]==201)
 ck('create untouched browser realm',req('/admin/realms','POST',{'realm':'mcp','enabled':True},a)[0]==201)
 with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=20) as discovery_response:
  discovery=json.loads(discovery_response.read(65536))
 jwks=urllib.parse.urlparse(discovery.get('jwks_uri',''))
 ck('GitHub discovery issuer/JWKS allowlist',discovery.get('issuer')==issuer and jwks.scheme=='https' and jwks.hostname=='token.actions.githubusercontent.com' and jwks.port in (None,443) and not jwks.username and not jwks.password and not jwks.fragment)
 idp={'alias':'synthetic-actions','providerId':'oidc','enabled':True,'hideOnLogin':True,'config':{'issuer':issuer,'clientId':'unused-synthetic','authorizationUrl':issuer+'/authorize','tokenUrl':issuer+'/token','validateSignature':'true','useJwksUrl':'true','jwksUrl':discovery['jwks_uri'],'supportsClientAssertions':'true','supportsClientAssertionReuse':'false','allowedClockSkew':'0'}}
 ck('create synthetic assertion trust',req('/admin/realms/'+realm+'/identity-provider/instances','POST',idp,a)[0]==201)
 client={'clientId':'terraform-webhook-router','enabled':True,'publicClient':False,'clientAuthenticatorType':'federated-jwt','serviceAccountsEnabled':True,'standardFlowEnabled':False,'directAccessGrantsEnabled':False,'fullScopeAllowed':False,'attributes':{'jwt.credential.issuer':'synthetic-actions','jwt.credential.sub':subject}}
 ck('create federated-only manager',req('/admin/realms/'+realm+'/clients','POST',client,a)[0]==201)
 _,cs=req('/admin/realms/'+realm+'/clients?clientId=terraform-webhook-router',token=a);cid=cs[0]['id']
 _,u=req('/admin/realms/'+realm+'/clients/'+cid+'/service-account-user',token=a)
 _,mg=req('/admin/realms/'+realm+'/clients?clientId=realm-management',token=a);mid=mg[0]['id']
 _,role=req('/admin/realms/'+realm+'/clients/'+mid+'/roles/manage-clients',token=a)
 ck('assign own-realm manage-clients only',req('/admin/realms/'+realm+'/users/'+u['id']+'/role-mappings/clients/'+mid,'POST',[role],a)[0]==204)
 ck('restrict manager role scope',req('/admin/realms/'+realm+'/clients/'+cid+'/scope-mappings/clients/'+mid,'POST',[role],a)[0]==204)
 def assertion(audience=None):
  url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']+'&audience='+urllib.parse.quote(audience or aud,safe='')
  if not url.startswith('https://'):raise RuntimeError('OIDC_ENDPOINT_NOT_HTTPS')
  request=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
  with urllib.request.urlopen(request,timeout=20) as response:value=json.loads(response.read(65536))['value']
  p=json.loads(base64.urlsafe_b64decode(value.split('.')[1]+'==='))
  # Exact reviewed context, never silently learn a subject from token input.
  expected={'iss':issuer,'sub':subject,'repository':'r33drichards/webhook-mcp-router','repository_id':'1432792940','repository_owner_id':'57335981','ref':'refs/heads/ci/keycloak-real-oidc-qualification'}
  if any(str(p.get(k))!=v for k,v in expected.items()) or p.get('aud')!=(audience or aud):raise RuntimeError('OIDC_CONTEXT_MISMATCH')
  return value
 def exchange(jwt):return req('/realms/'+realm+'/protocol/openid-connect/token','POST',{'grant_type':'client_credentials','client_id':'terraform-webhook-router','client_assertion_type':'urn:ietf:params:oauth:client-assertion-type:jwt-bearer','client_assertion':jwt},form=True)
 j=assertion();status,tok=exchange(j);ck('real GitHub assertion via HTTPS JWKS exchange',status==200)
 ck('real assertion replay rejected',exchange(j)[0] in (400,401))
 ck('real wrong-audience assertion rejected',exchange(assertion('https://wrong-audience.example.invalid'))[0] in (400,401))
 client['attributes']['jwt.credential.sub']=subject+'-wrong'
 ck('set temporary wrong-subject trust',req('/admin/realms/'+realm+'/clients/'+cid,'PUT',client,a)[0]==204)
 ck('real assertion against wrong subject rejected',exchange(assertion())[0] in (400,401))
 client['attributes']['jwt.credential.sub']=subject
 ck('restore exact subject',req('/admin/realms/'+realm+'/clients/'+cid,'PUT',client,a)[0]==204)
 idp['config']['issuer']='https://wrong-issuer.example.invalid'
 ck('set temporary wrong-issuer trust',req('/admin/realms/'+realm+'/identity-provider/instances/synthetic-actions','PUT',idp,a)[0]==204)
 ck('real assertion against wrong issuer rejected',exchange(assertion())[0] in (400,401))
 idp['config']['issuer']=issuer
 ck('restore exact issuer',req('/admin/realms/'+realm+'/identity-provider/instances/synthetic-actions','PUT',idp,a)[0]==204)
 parts=assertion().split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:]
 ck('tampered signature rejected',exchange('.'.join(parts))[0] in (400,401))
 ck('fresh real assertion accepted',exchange(assertion())[0]==200)
 token=tok['access_token'];claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
 ck('short-lived Keycloak token',0<claims['exp']-claims['iat']<=90)
 ck('Keycloak token issuer/subject',claims['iss']==aud and claims['sub']==u['id'])
 ck('own realm admin allowed',req('/admin/realms/'+realm+'/clients',token=token)[0]==200)
 ck('browser realm admin denied',req('/admin/realms/mcp/clients',token=token)[0]==403)
 ck('master realm admin denied',req('/admin/realms/master/clients',token=token)[0]==403)
 ck('new realm creation denied',req('/admin/realms','POST',{'realm':'forbidden'},token)[0]==403)
 tf=P/'terraform';tf.mkdir();src=Path(os.environ['GITHUB_WORKSPACE'])/'deploy/keycloak/terraform/realm'
 shutil.copy(src/'.terraform.lock.hcl',tf/'.terraform.lock.hcl')
 (tf/'main.tf').write_text("""
 terraform {
  required_version = "= 1.15.8"
  required_providers { keycloak = { source = "keycloak/keycloak", version = "= 5.10.0" } }
 }
 provider "keycloak" {
  url = "https://localhost:18444"
  realm = "webhook-router"
  client_id = "terraform-webhook-router"
  keycloak_version = "26.8.1"
  tls_insecure_skip_verify = false
 }
 resource "keycloak_openid_client" "probe" {
  realm_id = "webhook-router"
  client_id = "terraform-federation-probe"
  access_type = "PUBLIC"
  enabled = false
  standard_flow_enabled = false
  direct_access_grants_enabled = false
 }
 """)
 env={k:v for k,v in os.environ.items() if k not in ('ACTIONS_ID_TOKEN_REQUEST_TOKEN','ACTIONS_ID_TOKEN_REQUEST_URL','GITHUB_TOKEN','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','https_proxy','http_proxy','all_proxy')};env.update({'SSL_CERT_FILE':str(P/'server.crt'),'NO_PROXY':'','TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1'})
 # Go bypasses HTTP proxy for localhost; route using a local TCP tunnel instead.
 class TCPForward(socketserver.BaseRequestHandler):
  def handle(self):
   remote=original_connect((target_ip,8443))
   try:
    while True:
     ready,_,_=select.select([self.request,remote],[],[],10)
     if not ready:return
     for x in ready:
      data=x.recv(65536)
      if not data:return
      (remote if x is self.request else self.request).sendall(data)
   finally:remote.close()
 forward=socketserver.ThreadingTCPServer(('127.0.0.1',18444),TCPForward);forward.daemon_threads=True;threading.Thread(target=forward.serve_forever,daemon=True).start()
 def terraform(label,args):
  status,t=exchange(assertion());ck(label+' fresh federated token',status==200)
  env['KEYCLOAK_ACCESS_TOKEN']=t['access_token']
  run=subprocess.run(['terraform']+args,cwd=tf,env=env,capture_output=True,text=True,timeout=90)
    # Provider output is not emitted or retained; prevents token/plan leakage.
  ck(label,run.returncode==0)
 terraform('terraform-init',['init','-input=false','-no-color','-lockfile=readonly'])
 terraform('terraform-validate',['validate','-no-color'])
 terraform('terraform-apply',['apply','-auto-approve','-input=false','-no-color'])
 terraform('terraform-no-drift',['plan','-detailed-exitcode','-input=false','-no-color'])
 terraform('terraform-destroy',['destroy','-auto-approve','-input=false','-no-color'])
 expiring=assertion();expiry=json.loads(base64.urlsafe_b64decode(expiring.split('.')[1]+'==='))['exp']
 remaining=expiry-int(time.time())+2
 ck('expiry wait bounded',0<remaining<=650)
 print('Waiting for real assertion expiry (bounded 650 seconds).',flush=True)
 time.sleep(remaining)
 ck('expired real GitHub assertion rejected',exchange(expiring)[0] in (400,401))
 forward.shutdown();stop('federation')
 (P/'durations.json').write_text(json.dumps(durations));print('Real GitHub issuance/JWKS and Terraform qualification completed; assertions='+str(len(results)),flush=True)
finally:
 subprocess.run(['docker','rm','-f','router-federation-probe'],capture_output=True)
 root=Path(os.environ['RUNNER_TEMP'])/'router-real-oidc'
 if root.exists():
  result=subprocess.run(['docker','run','--rm','--network','none','--user','0:0','--entrypoint','/bin/bash','-v',str(root)+':/cleanup','quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b','-c','rm -rf /cleanup/data'],capture_output=True)
  if result.returncode!=0:raise RuntimeError('FIXTURE_DATA_CLEANUP_FAILED')
  shutil.rmtree(root)
 subprocess.run(['docker','network','rm','router-federation-isolated'],capture_output=True)
 names=subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
 networks=subprocess.check_output(['docker','network','ls','--format','{{.Name}}'],text=True).splitlines()
 if root.exists() or 'router-federation-probe' in names or 'router-federation-isolated' in networks:raise RuntimeError('FIXTURE_CLEANUP_INCOMPLETE')
 print('PASS fixture cleanup',flush=True)
