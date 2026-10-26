"""Closed app stage: unchanged foundation plus one disabled app, never activation."""
import importlib.util,json,re
from pathlib import Path
spec=importlib.util.spec_from_file_location('foundation',Path(__file__).with_name('azure-fresh-plan-check.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def validate(plan,digest):
 if not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('PACKAGE_DIGEST_REQUIRED')
 if base.validate(plan)!=13:raise ValueError('EXACT_DISABLED_APP_INVENTORY_REQUIRED')
 for row in plan['resource_changes']:
  change=row['change']
  if row['address']!='azapi_resource.app[0]':
   if change['actions']!=['no-op']:raise ValueError('FOUNDATION_CHANGE_NOT_APPROVED')
   continue
  if change['actions'] not in (['create'],['no-op']):raise ValueError('APP_UPDATE_NOT_IN_INITIAL_STAGE')
  a=change['after'];props=a['body']['properties'];settings={v['name']:v['value'] for v in props['siteConfig']['appSettings']}
  prefix=base.RG+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/webhook-mcp-router-v2-f7076f8e38-'
  ids={prefix+x for x in ('registry-reader','control','delivery')}
  identity=a.get('identity')
  if not isinstance(identity,list) or len(identity)!=1 or identity[0].get('type')!='SystemAssigned, UserAssigned' or set(identity[0].get('identity_ids',[]))!=ids:raise ValueError('RUNTIME_IDENTITY_BINDING')
  if props.get('keyVaultReferenceIdentity')!=prefix+'control':raise ValueError('SECRET_REFERENCE_IDENTITY')
  required={'WEBSITE_RUN_FROM_PACKAGE':f'https://whmcprv2f7076f8e38.blob.core.windows.net/router-packages/{digest}.zip','WEBSITE_RUN_FROM_PACKAGE_BLOB_MI_RESOURCE_ID':'SystemAssigned','AzureWebJobsStorage__accountName':'whmcprv2f7076f8e38','AzureWebJobsStorage__credential':'managedidentity','RouterQueue__queueServiceUri':'https://whmcprv2f7076f8e38.queue.core.windows.net','RouterQueue__credential':'managedidentity'}
  for setting,secret in [('ROUTER_AUTH_JSON','router-auth'),('ROUTER_TENANTS_JSON','router-tenants'),('ROUTER_DELIVERY_KEYS_JSON','router-delivery-keys')]:required[setting]=f'@Microsoft.KeyVault(SecretUri=https://kv-whmcprv2-f7076f8e38.vault.azure.net/secrets/{secret}/)'
  for key,value in required.items():
   if settings.get(key)!=value:raise ValueError('PACKAGE_OR_CONFIG_REFERENCE_BINDING')
 return 13
if __name__=='__main__':
 import sys
 try:print('PASS disabled app plan; resources='+str(validate(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])))
 except Exception as e:
  allowed={'PACKAGE_DIGEST_REQUIRED','EXACT_DISABLED_APP_INVENTORY_REQUIRED','FOUNDATION_CHANGE_NOT_APPROVED','APP_UPDATE_NOT_IN_INITIAL_STAGE','RUNTIME_IDENTITY_BINDING','SECRET_REFERENCE_IDENTITY','PACKAGE_OR_CONFIG_REFERENCE_BINDING'}
  print(base.safe_failure(e) if isinstance(e,base.GuardFailure) else 'FAIL DISABLED_APP_REASON='+(str(e) if str(e) in allowed else 'INVALID_PLAN_SHAPE'));raise SystemExit(1)
