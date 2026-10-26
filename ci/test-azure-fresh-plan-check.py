import importlib.util,json,copy
from pathlib import Path
s=importlib.util.spec_from_file_location('guard',Path(__file__).with_name('azure-fresh-plan-check.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[]
for addr,v in m.inventory().items():
 if addr.endswith('app[0]'):continue
 after=copy.deepcopy(v)
 if addr.endswith('sql_server'):
  after.update(location='westus2',body={'properties':{'version':'12.0','minimalTlsVersion':'1.2','publicNetworkAccess':'Disabled','administrators':{'administratorType':'ActiveDirectory','principalType':'User','login':'synthetic@example.invalid','sid':'00000000-0000-0000-0000-000000000001','tenantId':'0e4545fd-804f-4acb-ad41-f955e53645c1','azureADOnlyAuthentication':True}}})
 if addr.endswith('sql_database'):
  after.update(location='westus2',body={'sku':{'name':'GP_S_Gen5','tier':'GeneralPurpose','family':'Gen5','capacity':2},'properties':{'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','autoPauseDelay':60,'minCapacity':0.5,'maxSizeBytes':34359738368,'requestedBackupStorageRedundancy':'Local','zoneRedundant':False}})
 rows.append({'address':addr,'mode':'managed','type':'azapi_resource','change':{'actions':['create'],'after':after}})
p={'format_version':'1.2','terraform_version':'1.15.8','complete':True,'errored':False,'resource_changes':rows}
assert m.validate(p)==12
checks=1
def rejected(q):
 global checks
 try:m.validate(q)
 except (ValueError,TypeError,KeyError):checks+=1;return
 raise AssertionError('Unsafe replacement plan accepted')
def mutate(plan,addr,path,value):
 q=copy.deepcopy(plan);node=next(r for r in q['resource_changes'] if r['address']==addr)['change']['after']
 for k in path[:-1]:node=node[k]
 node[path[-1]]=value;rejected(q)
for acts in [['delete'],['delete','create'],['read']]:
 q=copy.deepcopy(p);q['resource_changes'][0]['change']['actions']=acts;rejected(q)
q=copy.deepcopy(p);q['resource_changes'][0]['change']['importing']={'id':'old'};rejected(q)
q=copy.deepcopy(p);q['resource_changes'][0]['address']='azapi_resource.old_state';rejected(q)
q=copy.deepcopy(p);q['resource_changes'].pop();rejected(q)
for addr,path,value in [
 ('foundation["plan"]',['body','sku','name'],'P1v3'),
 ('foundation["plan"]',['body','sku','tier'],'PremiumV3'),
 ('foundation["plan"]',['body','properties','reserved'],True),
 ('foundation["plan"]',['parent_id'],m.RG.replace('-v2','-poc')),
 ('foundation["plan"]',['location'],'eastus'),
 ('foundation["storage"]',['body','sku','name'],'Premium_LRS'),
 ('foundation["storage"]',['body','properties','allowBlobPublicAccess'],True),
 ('foundation["storage"]',['body','properties','allowSharedKeyAccess'],True),
 ('foundation["storage"]',['body','properties','supportsHttpsTrafficOnly'],False),
 ('foundation["storage"]',['body','properties','minimumTlsVersion'],'TLS1_0'),
 ('storage_children["packages"]',['body','properties','publicAccess'],'Blob'),
 ('storage_children["host_leases"]',['body','properties','publicAccess'],'Container'),
 ('storage_children["host_secrets"]',['parent_id'],m.RG.replace('-v2','-poc')),
 ('sql_database',['body','properties','freeLimitExhaustionBehavior'],'BillForUsage'),
 ('sql_database',['body','properties','useFreeLimit'],False),
 ('sql_database',['body','sku','capacity'],4),
 ('sql_database',['body','properties','minCapacity'],1),
 ('sql_database',['body','properties','maxSizeBytes'],68719476736),
 ('sql_database',['body','properties','autoPauseDelay'],-1),
 ('sql_database',['body','properties','requestedBackupStorageRedundancy'],'Geo'),
 ('sql_server',['body','properties','publicNetworkAccess'],'Enabled'),
 ('sql_server',['body','properties','administrators','azureADOnlyAuthentication'],False),
]:mutate(p,'azapi_resource.'+addr,path,value)
app=copy.deepcopy(m.inventory()['azapi_resource.app[0]'])
app.update(location='westus2',body={'kind':'functionapp','properties':{'enabled':False,'publicNetworkAccess':'Disabled','dailyMemoryTimeQuota':1000,'httpsOnly':True,'serverFarmId':m.RG+'/providers/Microsoft.Web/serverfarms/asp-webhook-mcp-router-v2','siteConfig':{'functionAppScaleLimit':1,'alwaysOn':False,'use32BitWorkerProcess':False,'netFrameworkVersion':'v10.0','ftpsState':'Disabled','minTlsVersion':'1.2','scmMinTlsVersion':'1.2','remoteDebuggingEnabled':False,'scmIpSecurityRestrictionsUseMain':False,'ipSecurityRestrictionsDefaultAction':'Deny','scmIpSecurityRestrictionsDefaultAction':'Deny','ipSecurityRestrictions':[],'scmIpSecurityRestrictions':[],'appSettings':[{'name':k,'value':v} for k,v in {'ROUTER_DISPATCH_ENABLED':'false','AzureWebJobs.RouterDispatch.Disabled':'true','AzureWebJobs.RouterReconcile.Disabled':'true'}.items()]}}})
q=copy.deepcopy(p);q['resource_changes'].append({'address':'azapi_resource.app[0]','mode':'managed','type':'azapi_resource','change':{'actions':['create'],'after':app}})
assert m.validate(q)==13;checks+=1
for field,value in [('enabled',True),('publicNetworkAccess','Enabled'),('dailyMemoryTimeQuota',0),('dailyMemoryTimeQuota',1001),('httpsOnly',False),('serverFarmId','old-plan')]:mutate(q,'azapi_resource.app[0]',['body','properties',field],value)
for field,value in [('functionAppScaleLimit',2),('functionAppScaleLimit',True),('alwaysOn',True),('ftpsState','AllAllowed'),('remoteDebuggingEnabled',True),('minTlsVersion','1.0'),('appSettings',[]),('ipSecurityRestrictions',[{'action':'Allow','ipAddress':'0.0.0.0/0'}]),('scmIpSecurityRestrictions',[{'action':'Allow','ipAddress':'0.0.0.0/0'}])]:mutate(q,'azapi_resource.app[0]',['body','properties','siteConfig',field],value)
assert m.validate(p,foundation_only=True)==12;checks+=1
for sample,options in [(q,{'foundation_only':True}),(p,{'require_noop':True})]:
 try:m.validate(sample,**options)
 except ValueError:checks+=1
 else:raise AssertionError('Foundation/postapply boundary accepted')
noop=copy.deepcopy(p)
for row in noop['resource_changes']:row['change']['actions']=['no-op']
assert m.validate(noop,foundation_only=True,require_noop=True)==12;checks+=1
print(f'PASS {checks} fresh-plan cost/security guard fixtures (no live lifecycle executed)')

# Diagnostics must never serialize values, exception text or unknown resource names.
assert m.safe_failure(m.GuardFailure('POST_APPLY_DRIFT','azapi_resource.sql_database'))=='FAIL GUARD_REASON=POST_APPLY_DRIFT RESOURCE_KEY=sql_database'
assert m.safe_failure(m.GuardFailure('secret-marker','secret-address'))=='FAIL GUARD_REASON=INVALID_PLAN_SHAPE RESOURCE_KEY=UNRECOGNIZED_RESOURCE'
assert m.safe_failure(ValueError('secret-marker'))=='FAIL GUARD_REASON=INVALID_PLAN_SHAPE RESOURCE_KEY=PLAN'
print('PASS 3 diagnostic allowlist checks; private values and arbitrary exception text withheld')

# Observed Azure response representation: base SKU and separate capacity.
# No action is exempted: a proposed update still fails the strict no-op gate.
canonical=copy.deepcopy(noop)
assert m.validate(canonical,foundation_only=True,require_noop=True)==12
for name,capacity in [('GP_S_Gen5_2',2),('GP_S_Gen5',4),('GP_Gen5',2)]:
 bad=copy.deepcopy(canonical)
 db=next(r for r in bad['resource_changes'] if r['address']=='azapi_resource.sql_database')
 db['change']['after']['body']['sku'].update(name=name,capacity=capacity)
 try:m.validate(bad,foundation_only=True,require_noop=True)
 except ValueError:pass
 else:raise AssertionError('Noncanonical or changed-capacity SQL accepted')
bad=copy.deepcopy(canonical)
next(r for r in bad['resource_changes'] if r['address']=='azapi_resource.sql_database')['change']['actions']=['update']
try:m.validate(bad,foundation_only=True,require_noop=True)
except m.GuardFailure as error:assert error.reason=='POST_APPLY_DRIFT'
else:raise AssertionError('SQL update bypassed no-op requirement')
print('PASS 5 canonical SQL representation regressions; strict no-op unchanged')
