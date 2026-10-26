import runpy,importlib.util,copy
from pathlib import Path
root=Path(__file__).parent
fixtures=runpy.run_path(str(root/'test-azure-fresh-plan-check.py'))
s=importlib.util.spec_from_file_location('stage',root/'azure-disabled-app-plan-check.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=copy.deepcopy(fixtures['q']);digest='2c286c45033558bae23798247249411bb080aabba1fd710751e47878e791782c'
for row in p['resource_changes']:
 if row['address']!='azapi_resource.app[0]':row['change']['actions']=['no-op']
app=p['resource_changes'][-1]['change']['after'];prefix=m.base.RG+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/webhook-mcp-router-v2-f7076f8e38-'
app['identity']=[{'type':'SystemAssigned, UserAssigned','identity_ids':[prefix+x for x in ('registry-reader','control','delivery')]}]
props=app['body']['properties'];props['keyVaultReferenceIdentity']=prefix+'control'
settings={'WEBSITE_RUN_FROM_PACKAGE':f'https://whmcprv2f7076f8e38.blob.core.windows.net/router-packages/{digest}.zip','WEBSITE_RUN_FROM_PACKAGE_BLOB_MI_RESOURCE_ID':'SystemAssigned','AzureWebJobsStorage__accountName':'whmcprv2f7076f8e38','AzureWebJobsStorage__credential':'managedidentity','RouterQueue__queueServiceUri':'https://whmcprv2f7076f8e38.queue.core.windows.net','RouterQueue__credential':'managedidentity'}
for key,name in [('ROUTER_AUTH_JSON','router-auth'),('ROUTER_TENANTS_JSON','router-tenants'),('ROUTER_DELIVERY_KEYS_JSON','router-delivery-keys')]:settings[key]=f'@Microsoft.KeyVault(SecretUri=https://kv-whmcprv2-f7076f8e38.vault.azure.net/secrets/{name}/)'
props['siteConfig']['appSettings'] += [{'name':k,'value':v} for k,v in settings.items()]
settings_extra={'FUNCTIONS_EXTENSION_VERSION':'~4','FUNCTIONS_WORKER_RUNTIME':'dotnet-isolated','OPA_EXECUTABLE':r'D:\home\site\wwwroot\tools\opa.exe','OPA_CAPABILITIES':r'D:\home\site\wwwroot\policies\capabilities.json'}
props['siteConfig']['appSettings'] += [{'name':k,'value':v} for k,v in settings_extra.items()]
p['configuration']={'root_module':{'resources':[{'address':'azapi_resource.app','expressions':{'body':{'references':['var.app_enabled']}}}]}}
assert m.validate(p,digest)==13
cases=[]
x=copy.deepcopy(p);x['resource_changes'][0]['change']['actions']=['update'];cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['actions']=['update'];cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['body']['properties']['enabled']=True;cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['identity'][0]['identity_ids'].append('unapproved');cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['body']['properties']['keyVaultReferenceIdentity']=prefix+'delivery';cases.append(x)
x=copy.deepcopy(p);next(v for v in x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'] if v['name']=='WEBSITE_RUN_FROM_PACKAGE')['value']='https://unapproved.invalid/package.zip';cases.append(x)
for key in ('AzureWebJobsStorage__clientId','RouterQueue__clientId','WEBSITE_CONTENTAZUREFILECONNECTIONSTRING','WEBSITE_CONTENTSHARE','UNAPPROVED_PLAINTEXT'):
 x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'].append({'name':key,'value':'synthetic-only'});cases.append(x)
for path,key in ((['siteConfig'],'azureStorageAccounts'),(['siteConfig'],'connectionStrings'),([],'storageAccountRequired')):
 x=copy.deepcopy(p);target=x['resource_changes'][-1]['change']['after']['body']['properties']
 for part in path:target=target[part]
 target[key]={};cases.append(x)
for key in ('sensitive_body','sensitive_body_version'):
 for section in ('before','after','after_unknown'):
  x=copy.deepcopy(p);x['resource_changes'][-1]['change'].setdefault(section,{})[key]=True if section=='after_unknown' else {'properties':{'enabled':True,'publicNetworkAccess':'Enabled'}};cases.append(x)
 for expression in ({'constant_value':None},{'references':['var.hidden_override']}):
  x=copy.deepcopy(p);x['configuration']['root_module']['resources'][0]['expressions'][key]=expression;cases.append(x)
x=copy.deepcopy(p);del x['configuration'];cases.append(x)
x=copy.deepcopy(p);entries=x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'];entries.append(copy.deepcopy(entries[0]));cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'][0]['extra']='unapproved';cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'][0]['value']=None;cases.append(x)
# Provider-schema null defaults are harmless; configured null expressions are not.
null_defaults=copy.deepcopy(p)
null_defaults['resource_changes'][-1]['change']['after'].update(sensitive_body=None,sensitive_body_version=None)
assert m.validate(null_defaults,digest)==13
for value in (False,{},'synthetic-only'):
 x=copy.deepcopy(p);x['resource_changes'][-1]['change']['after']['sensitive_body']=value;cases.append(x)
x=copy.deepcopy(p);x['configuration']['root_module']['module_calls']={'extra':{'module':{'resources':[{'address':'azapi_resource.extra','expressions':{'sensitive_body':{'constant_value':{}}}}]}}};cases.append(x)
for x in cases:
 try:m.validate(x,digest)
 except ValueError:pass
 else:raise AssertionError('Unsafe staging plan accepted')
print(f'PASS {2+len(cases)} disabled-app stage fixtures; no Azure plan/apply or package upload')
