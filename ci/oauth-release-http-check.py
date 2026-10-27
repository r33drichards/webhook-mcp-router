"""Public, credential-free discovery/auth-denial verification. Never print bodies."""
import json,time,urllib.request,urllib.error
ORIGIN='https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net'
RESOURCE=ORIGIN+'/api/mcp'
METADATA=ORIGIN+'/.well-known/oauth-protected-resource/api/mcp'
ISSUER='https://keycloak-production-295b.up.railway.app/realms/webhook-router'
CHALLENGE='Bearer resource_metadata="'+METADATA+'", scope="router:read"'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def check(fetch):
 status,headers,body=fetch(METADATA,'GET',False)
 assert status==200 and headers.get('Content-Type','').lower().startswith('application/json')
 doc=json.loads(body)
 assert doc=={'resource':RESOURCE,'authorization_servers':[ISSUER],'scopes_supported':['router:read','requests:read','destinations:read','policies:read','policies:test','policies:write'],'bearer_methods_supported':['header']}
 for method in ('GET','POST'):
  for invalid in (False,True):
   status,headers,_=fetch(RESOURCE,method,invalid)
   assert status==401 and headers.get('WWW-Authenticate')==CHALLENGE
 status,_,_=fetch(ORIGIN+'/api/.well-known/oauth-protected-resource/api/mcp','GET',False)
 assert status==404

def fetch(url,method,invalid):
 headers={'Accept':'application/json'}
 if invalid:headers['Authorization']='Bearer synthetic-invalid-release-check'
 request=urllib.request.Request(url,method=method,headers=headers,data=b'{}' if method=='POST' else None)
 try: response=urllib.request.build_opener(NoRedirect).open(request,timeout=20)
 except urllib.error.HTTPError as error:response=error
 with response:
  body=response.read(16385)
  assert len(body)<=16384
  return response.status,response.headers,body

if __name__=='__main__':
 for attempt in range(30):
  try:
   check(fetch)
   print('PASS hosted OAuth discovery; missing/invalid tokens denied; no authenticated login claimed')
   break
  except (AssertionError,ValueError,OSError,urllib.error.URLError):
   if attempt==29:raise SystemExit('FAIL HOSTED_DISCOVERY_OR_AUTH_DENIAL; no raw response logged')
   time.sleep(10)
