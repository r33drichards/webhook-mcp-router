import importlib.util,json,copy
from pathlib import Path
s=importlib.util.spec_from_file_location('guard',Path(__file__).with_name('azure-fresh-plan-check.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[]
for addr,v in m.inventory().items():
 if addr.endswith('app[0]'):continue
 after=copy.deepcopy(v)
 if addr.endswith('sql_server'):after['body']={'properties':{'publicNetworkAccess':'Disabled'}}
 if addr.endswith('sql_database'):after['body']={'properties':{'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','autoPauseDelay':60}}
 rows.append({'address':addr,'mode':'managed','type':'azapi_resource','change':{'actions':['create'],'after':after}})
p={'format_version':'1.2','terraform_version':'1.15.8','complete':True,'errored':False,'resource_changes':rows}
assert m.validate(p)==10
bad=[]
for acts in [['delete'],['delete','create'],['read']]:
 q=copy.deepcopy(p);q['resource_changes'][0]['change']['actions']=acts;bad.append(q)
q=copy.deepcopy(p);q['resource_changes'][0]['change']['importing']={'id':'old'};bad.append(q)
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after']['parent_id']=m.RG.replace('-v2','-poc');bad.append(q)
q=copy.deepcopy(p);q['resource_changes'][0]['address']='azapi_resource.old_state';bad.append(q)
q=copy.deepcopy(p);q['resource_changes'].pop();bad.append(q)
q=copy.deepcopy(p);q['resource_changes'][-1]['change']['after']['body']['properties']['freeLimitExhaustionBehavior']='BillForUsage';bad.append(q)
for q in bad:
 try:m.validate(q)
 except ValueError:continue
 raise AssertionError('Unsafe replacement plan accepted')
app=copy.deepcopy(m.inventory()['azapi_resource.app[0]'])
app['body']={'properties':{'enabled':False,'publicNetworkAccess':'Disabled','siteConfig':{'ipSecurityRestrictionsDefaultAction':'Deny','scmIpSecurityRestrictionsDefaultAction':'Deny','ipSecurityRestrictions':[],'scmIpSecurityRestrictions':[],'appSettings':[{'name':k,'value':v} for k,v in {'ROUTER_DISPATCH_ENABLED':'false','AzureWebJobs.RouterDispatch.Disabled':'true','AzureWebJobs.RouterReconcile.Disabled':'true'}.items()]}}}
q=copy.deepcopy(p);q['resource_changes'].append({'address':'azapi_resource.app[0]','mode':'managed','type':'azapi_resource','change':{'actions':['create'],'after':app}})
assert m.validate(q)==11
for field,value in [('enabled',True),('publicNetworkAccess','Enabled')]:
 r=copy.deepcopy(q);r['resource_changes'][-1]['change']['after']['body']['properties'][field]=value
 try:m.validate(r)
 except ValueError:pass
 else:raise AssertionError('Unapproved activation accepted')
for field,value in [('appSettings',[]),('ipSecurityRestrictions',[{'action':'Allow','ipAddress':'0.0.0.0/0'}]),('scmIpSecurityRestrictions',[{'action':'Allow','ipAddress':'0.0.0.0/0'}])]:
 r=copy.deepcopy(q);r['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig'][field]=value
 try:m.validate(r)
 except ValueError:pass
 else:raise AssertionError('Unapproved dispatch or ingress accepted')
print('PASS 15 fresh-plan guard fixtures (no live lifecycle executed)')
