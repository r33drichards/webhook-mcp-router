"""Fresh closed-router plans only. Never adopt/delete old or shared resources."""
import json
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
        body=a.get('body') or {};props=body.get('properties',{})
        if addr=='azapi_resource.sql_database':
            if props.get('useFreeLimit') is not True or props.get('freeLimitExhaustionBehavior')!='AutoPause' or props.get('autoPauseDelay')!=60:raise ValueError('FREE_SQL_REQUIRED')
        if addr=='azapi_resource.sql_server' and props.get('publicNetworkAccess')!='Disabled':raise ValueError('SQL_OPENING_DENIED')
        if addr=='azapi_resource.app[0]':
            site=props.get('siteConfig',{})
            if props.get('enabled') is not False or props.get('publicNetworkAccess')!='Disabled' or site.get('ipSecurityRestrictionsDefaultAction')!='Deny' or site.get('scmIpSecurityRestrictionsDefaultAction')!='Deny':raise ValueError('ACTIVATION_DENIED')
            settings={s['name']:s['value'] for s in site.get('appSettings',[])}
            if any(k in settings for k in ('WEBSITE_CONTENTSHARE','WEBSITE_CONTENTAZUREFILECONNECTIONSTRING','AzureWebJobsStorage')):raise ValueError('STORAGE_SECRET_PATH_DENIED')
    if set(expected)-{'azapi_resource.app[0]'}-seen:raise ValueError('INCOMPLETE_INVENTORY')
    return len(seen)
if __name__=='__main__':
    import sys
    try: print('PASS fresh closed-router plan; resources='+str(validate(json.loads(Path(sys.argv[1]).read_text()))))
    except Exception: print('FAIL fresh-router plan; private details withheld');raise SystemExit(1)
