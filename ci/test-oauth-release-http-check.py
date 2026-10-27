import importlib.util,json
from pathlib import Path
s=importlib.util.spec_from_file_location('check',Path(__file__).with_name('oauth-release-http-check.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def fetch(url,method,invalid):
 if url==m.METADATA:return 200,{'Content-Type':'application/json'},json.dumps({'resource':m.RESOURCE,'authorization_servers':[m.ISSUER],'scopes_supported':['router:read','requests:read','destinations:read'],'bearer_methods_supported':['header']}).encode()
 if url==m.RESOURCE:return 401,{'WWW-Authenticate':m.CHALLENGE},b''
 return 404,{},b''
m.check(fetch)
for kind in ('metadata_redirect','wrong_issuer','missing_challenge','anonymous_success','invalid_success','old_prefix'):
 def bad(url,method,invalid):
  status,headers,body=fetch(url,method,invalid)
  if kind=='metadata_redirect' and url==m.METADATA:status=302
  if kind=='wrong_issuer' and url==m.METADATA:body=body.replace(m.ISSUER.encode(),b'https://wrong.invalid')
  if kind=='missing_challenge' and url==m.RESOURCE:headers={}
  if kind=='anonymous_success' and url==m.RESOURCE and not invalid:status=200
  if kind=='invalid_success' and url==m.RESOURCE and invalid:status=200
  if kind=='old_prefix' and url not in (m.METADATA,m.RESOURCE):status=200
  return status,headers,body
 try:m.check(bad)
 except AssertionError:pass
 else:raise AssertionError(kind)
assert m.NoRedirect().redirect_request(None,None,None,None,None,None) is None
print('PASS 8 public release HTTP verification fixtures; no network calls')
