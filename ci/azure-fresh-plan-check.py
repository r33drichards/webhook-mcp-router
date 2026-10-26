"""Fresh closed-router plans only. Never adopt/delete old or shared resources."""
import json
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'deploy/azure/terraform-fresh'
RG='/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-v2'
REASONS = frozenset(['ACTIVATION_DENIED', 'APP_COST_SECURITY_CONTRACT_MISMATCH', 'APP_CREATION_NOT_IN_FOUNDATION_APPLY', 'APP_LOCATION_KIND', 'APP_SITE_CONTRACT_MISMATCH', 'DEFERRED_OR_ACTION_PLAN', 'DELETE_REPLACE_OR_IMPORT_DENIED', 'DISPATCH_ACTIVATION_DENIED', 'FOUNDATION_CONTRACT_MISMATCH', 'FREE_SQL_REQUIRED', 'INCOMPLETE_INVENTORY', 'INCOMPLETE_OR_UNREVIEWED_PLAN', 'INGRESS_RULES_NOT_APPROVED', 'OUTSIDE_FRESH_INVENTORY', 'POST_APPLY_DRIFT', 'RESOURCE_BINDING_MISMATCH', 'SQL_COST_SECURITY_CONTRACT_MISMATCH', 'SQL_ENTRA_ONLY_REQUIRED', 'SQL_OPENING_DENIED', 'SQL_SERVER_CONTRACT_MISMATCH', 'STORAGE_CHILD_CONTRACT_MISMATCH', 'STORAGE_SECRET_PATH_DENIED', 'INVALID_PLAN_SHAPE'])
RESOURCE_KEYS = {
 'PLAN':'PLAN',
 **{'azapi_resource.foundation["'+k+'"]':'foundation.'+k for k in ('plan','storage','registry_reader','control','delivery')},
 **{'azapi_resource.storage_children["'+k+'"]':'storage_children.'+k for k in ('router_dispatch','router_dispatch_poison','packages','host_leases','host_secrets')},
 'azapi_resource.sql_server':'sql_server',
 'azapi_resource.sql_database':'sql_database',
 'azapi_resource.app[0]':'app',
}
class GuardFailure(ValueError):
 def __init__(self, reason, address='PLAN'):
  self.reason=reason if reason in REASONS else 'INVALID_PLAN_SHAPE'
  self.resource=RESOURCE_KEYS.get(address,'UNRECOGNIZED_RESOURCE')
  super().__init__(self.reason)
def safe_failure(error):
 if isinstance(error,GuardFailure):return f'FAIL GUARD_REASON={error.reason} RESOURCE_KEY={error.resource}'
 return 'FAIL GUARD_REASON=INVALID_PLAN_SHAPE RESOURCE_KEY=PLAN'

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
SQL_BODY={'sku':{'name':'GP_S_Gen5','tier':'GeneralPurpose','family':'Gen5','capacity':2},'properties':{'autoPauseDelay':60,'minCapacity':0.5,'maxSizeBytes':34359738368,'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','requestedBackupStorageRedundancy':'Local','zoneRedundant':False}}
def exact(value, expected):
    # JSON equality must not confuse true with 1, or false with 0.
    return json.dumps(value,sort_keys=True,separators=(',',':'))==json.dumps(expected,sort_keys=True,separators=(',',':'))
def contract(addr,a):
    body=a.get('body');props=(body or {}).get('properties',{})
    if addr.startswith('azapi_resource.foundation['):
        key=json.loads(addr.split('[',1)[1][:-1])
        wanted=PLAN_BODY if key=='plan' else STORAGE_BODY if key=='storage' else {}
        if not exact(body,wanted) or a.get('location')!='westus2':raise GuardFailure('FOUNDATION_CONTRACT_MISMATCH',addr)
    if addr.startswith('azapi_resource.storage_children['):
        wanted={'properties':{'publicAccess':'None'}} if any(addr.endswith('["'+key+'"]') for key in ('packages','host_leases','host_secrets')) else {'properties':{}}
        if not exact(body,wanted):raise GuardFailure('STORAGE_CHILD_CONTRACT_MISMATCH',addr)
    if addr=='azapi_resource.sql_database':
        if not exact(body,SQL_BODY) or a.get('location')!='westus2':raise GuardFailure('SQL_COST_SECURITY_CONTRACT_MISMATCH',addr)
    if addr=='azapi_resource.sql_server':
        admin=props.get('administrators',{})
        wanted={'version':'12.0','minimalTlsVersion':'1.2','publicNetworkAccess':'Disabled','administrators':admin}
        if not exact(body,{'properties':wanted}) or a.get('location')!='westus2':raise GuardFailure('SQL_SERVER_CONTRACT_MISMATCH',addr)
        if set(admin)!={'administratorType','principalType','login','sid','tenantId','azureADOnlyAuthentication'} or admin.get('administratorType')!='ActiveDirectory' or admin.get('principalType')!='User' or admin.get('tenantId')!='0e4545fd-804f-4acb-ad41-f955e53645c1' or admin.get('azureADOnlyAuthentication') is not True or not isinstance(admin.get('login'),str) or not admin['login'].strip():raise GuardFailure('SQL_ENTRA_ONLY_REQUIRED',addr)
        uuid.UUID(admin['sid'])
    if addr=='azapi_resource.app[0]':
        site=props.get('siteConfig',{})
        if a.get('location')!='westus2' or body.get('kind')!='functionapp':raise GuardFailure('APP_LOCATION_KIND',addr)
        for key,value in {'dailyMemoryTimeQuota':1000,'httpsOnly':True,'serverFarmId':RG+'/providers/Microsoft.Web/serverfarms/asp-webhook-mcp-router-v2'}.items():
            if not exact(props.get(key),value):raise GuardFailure('APP_COST_SECURITY_CONTRACT_MISMATCH',addr)
        for key,value in {'functionAppScaleLimit':1,'alwaysOn':False,'use32BitWorkerProcess':False,'netFrameworkVersion':'v10.0','ftpsState':'Disabled','minTlsVersion':'1.2','scmMinTlsVersion':'1.2','remoteDebuggingEnabled':False,'scmIpSecurityRestrictionsUseMain':False}.items():
            if not exact(site.get(key),value):raise GuardFailure('APP_SITE_CONTRACT_MISMATCH',addr)

def validate(plan, foundation_only=False, require_noop=False):
    addr="PLAN"
    if plan.get('format_version')!='1.2' or plan.get('terraform_version')!='1.15.8' or plan.get('complete') is not True or plan.get('errored') is not False:raise GuardFailure('INCOMPLETE_OR_UNREVIEWED_PLAN',addr)
    for key in ('deferred_changes','action_invocations','deferred_action_invocations'):
        if key in plan and plan[key]!=[]:raise GuardFailure('DEFERRED_OR_ACTION_PLAN',addr)
    expected=inventory();seen=set()
    for r in plan.get('resource_changes',[]):
        addr=r.get('address');c=r.get('change',{});a=c.get('after') or {}
        if addr not in expected or addr in seen or r.get('mode')!='managed' or r.get('type')!='azapi_resource':raise GuardFailure('OUTSIDE_FRESH_INVENTORY',addr)
        seen.add(addr)
        if foundation_only and addr=='azapi_resource.app[0]':raise GuardFailure('APP_CREATION_NOT_IN_FOUNDATION_APPLY',addr)
        if require_noop and c.get('actions')!=['no-op']:raise GuardFailure('POST_APPLY_DRIFT',addr)
        if c.get('actions') not in (['create'],['no-op'],['update']) or c.get('importing'):raise GuardFailure('DELETE_REPLACE_OR_IMPORT_DENIED',addr)
        for key in ('name','type','parent_id'):
            if a.get(key)!=expected[addr][key]:raise GuardFailure('RESOURCE_BINDING_MISMATCH',addr)
        contract(addr,a)
        body=a.get('body') or {};props=body.get('properties',{})
        if addr=='azapi_resource.sql_database':
            if props.get('useFreeLimit') is not True or props.get('freeLimitExhaustionBehavior')!='AutoPause' or props.get('autoPauseDelay')!=60:raise GuardFailure('FREE_SQL_REQUIRED',addr)
        if addr=='azapi_resource.sql_server' and props.get('publicNetworkAccess')!='Disabled':raise GuardFailure('SQL_OPENING_DENIED',addr)
        if addr=='azapi_resource.app[0]':
            site=props.get('siteConfig',{})
            if props.get('enabled') is not False or props.get('publicNetworkAccess')!='Disabled' or site.get('ipSecurityRestrictionsDefaultAction')!='Deny' or site.get('scmIpSecurityRestrictionsDefaultAction')!='Deny':raise GuardFailure('ACTIVATION_DENIED',addr)
            settings={s['name']:s['value'] for s in site.get('appSettings',[])}
            if settings.get('ROUTER_DISPATCH_ENABLED')!='false' or settings.get('AzureWebJobs.RouterDispatch.Disabled')!='true' or settings.get('AzureWebJobs.RouterReconcile.Disabled')!='true':raise GuardFailure('DISPATCH_ACTIVATION_DENIED',addr)
            if site.get('ipSecurityRestrictions')!=[] or site.get('scmIpSecurityRestrictions')!=[]:raise GuardFailure('INGRESS_RULES_NOT_APPROVED',addr)
            if any(k in settings for k in ('WEBSITE_CONTENTSHARE','WEBSITE_CONTENTAZUREFILECONNECTIONSTRING','AzureWebJobsStorage')):raise GuardFailure('STORAGE_SECRET_PATH_DENIED',addr)
    if set(expected)-{'azapi_resource.app[0]'}-seen:raise GuardFailure('INCOMPLETE_INVENTORY',addr)
    return len(seen)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('plan');parser.add_argument('--foundation-only',action='store_true');parser.add_argument('--require-noop',action='store_true');args=parser.parse_args()
    try: print('PASS fresh closed-router plan; resources='+str(validate(json.loads(Path(args.plan).read_text()),args.foundation_only,args.require_noop)))
    except Exception as error: print(safe_failure(error));raise SystemExit(1)
