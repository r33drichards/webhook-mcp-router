import copy, importlib.util, runpy
from pathlib import Path
root = Path(__file__).parent
fixture = runpy.run_path(str(root/'test-azure-disabled-app-plan-check.py'))
spec = importlib.util.spec_from_file_location('public', root/'azure-public-mcp-plan-check.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
p = copy.deepcopy(fixture['p'])
c = p['resource_changes'][-1]['change']; c['before'] = copy.deepcopy(c['after']); c['actions'] = ['update']
props = c['after']['body']['properties']; props['enabled'] = True; props['publicNetworkAccess'] = 'Enabled'
props['siteConfig']['ipSecurityRestrictionsDefaultAction'] = 'Allow'
c['after_unknown'] = {'output': True}
assert m.validate(p) == 13
noop = copy.deepcopy(p); nc = noop['resource_changes'][-1]['change']; nc['actions'] = ['no-op']; nc['before'] = copy.deepcopy(nc['after'])
assert m.validate(noop, True) == 13
cases = []
def altered(path, value, side='after'):
    x = copy.deepcopy(p); v = x['resource_changes'][-1]['change'][side]
    for k in path[:-1]: v = v[k]
    v[path[-1]] = value; cases.append(x)
for action in (['create'], ['delete'], ['delete','create']):
    x = copy.deepcopy(p); x['resource_changes'][-1]['change']['actions'] = action; cases.append(x)
for path, value in [
 (['body','properties','enabled'],1),
 (['body','properties','httpsOnly'],False),
 (['body','properties','dailyMemoryTimeQuota'],1001),
 (['body','properties','siteConfig','scmIpSecurityRestrictionsDefaultAction'],'Allow'),
 (['body','properties','siteConfig','scmIpSecurityRestrictionsUseMain'],True),
 (['body','properties','siteConfig','functionAppScaleLimit'],2),
 (['body','properties','siteConfig','ipSecurityRestrictions'],[{'action':'Allow','ipAddress':'0.0.0.0/0'}]),
 (['body','properties','siteConfig','azureStorageAccounts'],{}),
 (['identity'],[{'type':'SystemAssigned'}]),
 (['body','properties','keyVaultReferenceIdentity'],'wrong'),
]: altered(path,value)
for name in ('ROUTER_AUTH_JSON','WEBSITE_RUN_FROM_PACKAGE','ROUTER_DISPATCH_ENABLED','AzureWebJobs.RouterDispatch.Disabled','AzureWebJobs.RouterReconcile.Disabled','RouterQueue__credential'):
    x=copy.deepcopy(p); entries=x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings']
    next(e for e in entries if e['name']==name)['value']='unapproved'; cases.append(x)
for name in ('AzureWebJobsStorage__clientId','RouterQueue__clientId','WEBSITE_CONTENTSHARE','EXTRA_SECRET'):
    x=copy.deepcopy(p); x['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings'].append({'name':name,'value':'synthetic'}); cases.append(x)
for key in ('sensitive_body','sensitive_body_version'):
    altered([key],{})
    x=copy.deepcopy(p); x['configuration']['root_module']['resources'][0]['expressions'][key]={'constant_value':None}; cases.append(x)
for unknown in ({'body':True},{'identity':[{'principal_id':True}]},True):
    x=copy.deepcopy(p); x['resource_changes'][-1]['change']['after_unknown']=unknown; cases.append(x)
for action in (['update'],['create'],['delete']):
    x=copy.deepcopy(p); x['resource_changes'][0]['change']['actions']=action; cases.append(x)
x=copy.deepcopy(p); next(r for r in x['resource_changes'] if r['address']=='azapi_resource.sql_server')['change']['after']['body']['properties']['publicNetworkAccess']='Enabled'; cases.append(x)
x=copy.deepcopy(p); x['resource_changes'].append(copy.deepcopy(x['resource_changes'][0])); cases.append(x)
x=copy.deepcopy(p); x['output_changes']={'unexpected':{'actions':['update']}}; cases.append(x)
x=copy.deepcopy(p); x['action_invocations']=[{}]; cases.append(x)
# Unchanged but unsafe snapshots still fail the reused exact closed contract.
x=copy.deepcopy(p)
for side in ('before','after'): x['resource_changes'][-1]['change'][side]['body']['properties']['siteConfig']['scmIpSecurityRestrictionsDefaultAction']='Allow'
cases.append(x)
for x in cases:
    try: m.validate(x)
    except (ValueError, KeyError, TypeError): pass
    else: raise AssertionError('Unsafe activation accepted')
try: m.validate(p,True)
except ValueError: pass
else: raise AssertionError('Postapply update accepted')
print(f'PASS {len(cases)+3} public MCP activation cases; no cloud changes')

# Verify the prepared job cannot silently request SQL/dispatch/package changes.
w=(root.parent/'.github/workflows/azure-router-public-mcp.yml').read_text()
for expected in (
 "environment: azure-router", "github.ref == 'refs/heads/main'",
 "TF_VAR_sql_outbound_ips: '[]'", "TF_VAR_http_allowed_cidrs: '[]'",
 "TF_VAR_dispatch_enabled: 'false'", "TF_VAR_public_mcp_ingress: 'true'",
 'test "$GITHUB_SHA" = "$REVIEWED_COMMIT"',
 'test "$RUNTIME_CONFIG_VERIFIED" = true',
 'python3 ci/azure-disabled-app-deploy.py login',
 'python ../../../ci/azure-public-mcp-plan-check.py "$RUNNER_TEMP/router-post.json" --require-noop',
 'terraform apply -input=false -lock-timeout=60s "$RUNNER_TEMP/router.tfplan"',
 'if: always()',
): assert expected in w, expected
for forbidden in ('secrets.', 'az keyvault', 'az role assignment', 'actions: write', 'azure-disabled-app-deploy.py upload', 'azure-disabled-app-deploy.py package'):
 assert forbidden not in w, forbidden
print('PASS activation workflow scope/cleanup source contract')
