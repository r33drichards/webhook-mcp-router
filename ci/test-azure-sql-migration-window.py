import copy,importlib.util,os
from pathlib import Path
s=importlib.util.spec_from_file_location('window',Path(__file__).with_name('azure-sql-migration-window.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
os.environ['GITHUB_RUN_ID']='123';os.environ['GITHUB_RUN_ATTEMPT']='1'
state={'public':'Disabled','rules':[]};calls=[]
def fake(method,path,body=None):
 calls.append((method,path,body))
 if method=='get':return {'properties':{'publicNetworkAccess':state['public']}} if path==m.SERVER else {'value':copy.deepcopy(state['rules'])}
 if method=='patch':state['public']=body['properties']['publicNetworkAccess'];return {}
 if method=='put':state['rules']=[{'name':m.rule_name(),'properties':body['properties']}];return {}
 if method=='delete':
  assert state['public']=='Enabled','Azure rejects deletes while disabled'
  state['rules']=[r for r in state['rules'] if r['name']!=m.rule_name()];return {}
 raise AssertionError('unexpected call')
m.rest=fake;m.operation('open');m.operation('allow',{'sqlError':40615,'serverObservedTdsIpv4':'8.8.8.8'});m.operation('cleanup');assert state=={'public':'Disabled','rules':[]}
count=1
for ip in ['0.0.0.0','127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1','::1','8.8.8.8/32']:
 try:m.public_ip(ip)
 except ValueError:count+=1
 else:raise AssertionError('unsafe IP accepted')
state['rules']=[{'name':'unrelated','properties':{}}]
try:m.operation('open')
except ValueError:count+=1
else:raise AssertionError('existing rule ignored')
m.operation('cleanup');assert state['rules'][0]['name']=='unrelated';count+=1
state['public']='Enabled';state['rules']=[{'name':m.rule_name(),'properties':{}}]
def fail_delete(method,path,body=None):
 if method=='delete':raise ValueError('synthetic API error')
 return fake(method,path,body)
m.rest=fail_delete
try:m.operation('cleanup')
except ValueError:assert state['public']=='Disabled';count+=1
else:raise AssertionError('cleanup failure concealed')
m.rest=fake
# Disabled with a residual owned rule must fail closed, never reopen silently.
state['public']='Disabled';calls.clear()
try:m.operation('cleanup')
except ValueError:
 assert state['public']=='Disabled' and state['rules']
 assert not any(c[0]=='patch' and c[2]['properties']['publicNetworkAccess']=='Enabled' for c in calls)
 count+=1
else:raise AssertionError('residual rule concealed')
# Normal path deletes before disabling, while preserving an unrelated rule.
state['public']='Enabled';state['rules'].append({'name':'unrelated','properties':{}});calls.clear()
m.operation('cleanup')
assert state=={'public':'Disabled','rules':[{'name':'unrelated','properties':{}}]}
assert next(i for i,c in enumerate(calls) if c[0]=='delete') < next(i for i,c in enumerate(calls) if c[0]=='patch')
count+=1
print(f'PASS {count} offline SQL window cases; no Azure operations')
