"""Fresh closed-router plans only. Never adopt/delete old or shared resources."""
import json
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'deploy/azure/terraform-fresh'
RG='/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-v2'
def inventory():
    result={}
    for block,filename in [('foundation','resources.json'),('storage_children','storage-children.json')]:
        for key,value in json.loads((ROOT/filename).read_text()).items():result[f'azapi_resource.{block}[{json.dumps(key)}]']=value
    result['azapi_resource.sql_server']={'type':'Microsoft.Sql/servers@2023-08-01','name':'sql-webhook-mcp-router-v2-f7076f8e38','parent_id':RG}
    result['azapi_resource.sql_database']={'type':'Microsoft.Sql/servers/databases@2023-08-01','name':'router','parent_id':RG+'/providers/Microsoft.Sql/servers/sql-webhook-mcp-router-v2-f7076f8e38'}
    result['azapi_resource.app[0]']={'type':'Microsoft.Web/sites@2024-04-01','name':'webhook-mcp-router-v2-f7076f8e38','parent_id':RG}
    return result

# Independent approved contract: changing resource JSON alone cannot relax it.
PLAN_BODY={'sku':{'name':'Y1','tier':'Dynamic'},'properties':{'reserved':False}}
STORAGE_BODY={'kind':'StorageV2','sku':{'name':'Standard_LRS'},'properties':{'supportsHttpsTrafficOnly':True,'minimumTlsVersion':'TLS1_2','allowBlobPublicAccess':False,'allowSharedKeyAccess':False}}
SQL_BODY={'sku':{'name':'GP_S_Gen5_2','tier':'GeneralPurpose','family':'Gen5','capacity':2},'properties':{'autoPauseDelay':60,'minCapacity':0.5,'maxSizeBytes':34359738368,'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','requestedBackupStorageRedundancy':'Local','zoneRedundant':False}}
def exact(value, expected):
    # JSON equality must not confuse true with 1, or false with 0.
    return json.dumps(value,sort_keys=True,separators=(',',':'))==json.dumps(expected,sort_keys=True,separators=(',',':'))
def contract(addr,a):
    body=a.get('body');props=(body or {}).get('properties',{})
    if addr.startswith('azapi_resource.foundation['):
        key=json.loads(addr.split('[',1)[1][:-1])
        wanted=PLAN_BODY if key=='plan' else STORAGE_BODY if key=='storage' else {}
        if not exact(body,wanted) or a.get('location')!='westus2':raise ValueError('FOUNDATION_CONTRACT_MISMATCH')
    if addr.startswith('azapi_resource.storage_children['):
        wanted={'properties':{'publicAccess':'None'}} if addr.endswith('["packages"]') else {'properties':{}}
        if not exact(body,wanted):raise ValueError('STORAGE_CHILD_CONTRACT_MISMATCH')
    if addr=='azapi_resource.sql_database':
        if not exact(body,SQL_BODY) or a.get('location')!='westus2':raise ValueError('SQL_COST_SECURITY_CONTRACT_MISMATCH')
    if addr=='azapi_resource.sql_server':
        admin=props.get('administrators',{})
        wanted={'version':'12.0','minimalTlsVersion':'1.2','publicNetworkAccess':'Disabled','administrators':admin}
        if not exact(body,{'properties':wanted}) or a.get('location')!='westus2':raise ValueError('SQL_SERVER_CONTRACT_MISMATCH')
        if set(admin)!={'administratorType','principalType','login','sid','tenantId','azureADOnlyAuthentication'} or admin.get('administratorType')!='ActiveDirectory' or admin.get('principalType')!='User' or admin.get('tenantId')!='0e4545fd-804f-4acb-ad41-f955e53645c1' or admin.get('azureADOnlyAuthentication') is not True or not isinstance(admin.get('login'),str) or not admin['login'].strip():raise ValueError('SQL_ENTRA_ONLY_REQUIRED')
        uuid.UUID(admin['sid'])
    if addr=='azapi_resource.app[0]':
        site=props.get('siteConfig',{})
        if a.get('location')!='westus2' or body.get('kind')!='functionapp':raise ValueError('APP_LOCATION_KIND')
        for key,value in {'dailyMemoryTimeQuota':1000,'httpsOnly':True,'serverFarmId':RG+'/providers/Microsoft.Web/serverfarms/asp-webhook-mcp-router-v2'}.items():
            if not exact(props.get(key),value):raise ValueError('APP_COST_SECURITY_CONTRACT_MISMATCH')
        for key,value in {'functionAppScaleLimit':1,'alwaysOn':False,'use32BitWorkerProcess':False,'netFrameworkVersion':'v10.0','ftpsState':'Disabled','minTlsVersion':'1.2','scmMinTlsVersion':'1.2','remoteDebuggingEnabled':False,'scmIpSecurityRestrictionsUseMain':False}.items():
            if not exact(site.get(key),value):raise ValueError('APP_SITE_CONTRACT_MISMATCH')

def validate(plan):
    if plan.get('format_version')!='1.2' or plan.get('terraform_version')!='1.15.8' or plan.get('complete') is not True or plan.get('errored') is not False:raise ValueError('INCOMPLETE_OR_UNREVIEWED_PLAN')
    for key in ('deferred_changes','action_invocations','deferred_action_invocations'):
        if key in plan and plan[key]!=[]:raise ValueError('DEFERRED_OR_ACTION_PLAN')
    expected=inventory();seen=set()
    for r in plan.get('resource_changes',[]):
        addr=r.get('address');c=r.get('change',{});a=c.get('after') or {}
        if addr not in expected or addr in seen or r.get('mode')!='managed' or r.get('type')!='azapi_resource':raise ValueError('OUTSIDE_FRESH_INVENTORY')
        seen.add(addr)
        if c.get('actions') not in (['create'],['no-op'],['update']) or c.get('importing'):raise ValueError('DELETE_REPLACE_OR_IMPORT_DENIED')
        for key in ('name','type','parent_id'):
            if a.get(key)!=expected[addr][key]:raise ValueError('RESOURCE_BINDING_MISMATCH')
        contract(addr,a)
        body=a.get('body') or {};props=body.get('properties',{})
        if addr=='azapi_resource.sql_database':
            if props.get('useFreeLimit') is not True or props.get('freeLimitExhaustionBehavior')!='AutoPause' or props.get('autoPauseDelay')!=60:raise ValueError('FREE_SQL_REQUIRED')
        if addr=='azapi_resource.sql_server' and props.get('publicNetworkAccess')!='Disabled':raise ValueError('SQL_OPENING_DENIED')
        if addr=='azapi_resource.app[0]':
            site=props.get('siteConfig',{})
            if props.get('enabled') is not False or props.get('publicNetworkAccess')!='Disabled' or site.get('ipSecurityRestrictionsDefaultAction')!='Deny' or site.get('scmIpSecurityRestrictionsDefaultAction')!='Deny':raise ValueError('ACTIVATION_DENIED')
            settings={s['name']:s['value'] for s in site.get('appSettings',[])}
            if settings.get('ROUTER_DISPATCH_ENABLED')!='false' or settings.get('AzureWebJobs.RouterDispatch.Disabled')!='true' or settings.get('AzureWebJobs.RouterReconcile.Disabled')!='true':raise ValueError('DISPATCH_ACTIVATION_DENIED')
            if site.get('ipSecurityRestrictions')!=[] or site.get('scmIpSecurityRestrictions')!=[]:raise ValueError('INGRESS_RULES_NOT_APPROVED')
            if any(k in settings for k in ('WEBSITE_CONTENTSHARE','WEBSITE_CONTENTAZUREFILECONNECTIONSTRING','AzureWebJobsStorage')):raise ValueError('STORAGE_SECRET_PATH_DENIED')
    if set(expected)-{'azapi_resource.app[0]'}-seen:raise ValueError('INCOMPLETE_INVENTORY')
    return len(seen)
if __name__=='__main__':
    import sys
    try: print('PASS fresh closed-router plan; resources='+str(validate(json.loads(Path(sys.argv[1]).read_text()))))
    except Exception: print('FAIL fresh-router plan; private details withheld');raise SystemExit(1)
