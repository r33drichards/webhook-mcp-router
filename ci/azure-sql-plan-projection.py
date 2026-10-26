"""Safe SQL plan projection. No state values outside the fixed cost/security fields."""
import json,math,copy
from pathlib import Path
ADDRESS='azapi_resource.sql_database'
ENUMS={
 'body.sku.name':{'GP_S_Gen5','GP_S_Gen5_2'},
 'body.sku.tier':{'GeneralPurpose'},
 'body.sku.family':{'Gen5'},
 'body.properties.freeLimitExhaustionBehavior':{'AutoPause','BillForUsage'},
 'body.properties.requestedBackupStorageRedundancy':{'Local','Geo','Zone','GeoZone'},
 'body.properties.currentServiceObjectiveName':{'GP_S_Gen5_2'},
 'body.properties.requestedServiceObjectiveName':{'GP_S_Gen5_2'},
}
NUMBERS={'body.sku.capacity','body.properties.minCapacity','body.properties.maxSizeBytes','body.properties.autoPauseDelay'}
BOOLEANS={'body.properties.useFreeLimit','body.properties.zoneRedundant'}
FIELDS=sorted(set(ENUMS)|NUMBERS|BOOLEANS)
MISSING=object()
def value_at(obj,path):
 for part in path.split('.'):
  if not isinstance(obj,dict) or part not in obj:return MISSING
  obj=obj[part]
 return obj
def safe_value(path,value,unknown=False,sensitive=False):
 if sensitive:return {'status':'sensitive-withheld'}
 if unknown:return {'status':'unknown'}
 if value is MISSING:return {'status':'absent'}
 if value is None:return {'status':'null'}
 if path in ENUMS and type(value) is str and value in ENUMS[path]:return {'value':value}
 if path in BOOLEANS and type(value) is bool:return {'value':value}
 if path in NUMBERS and type(value) in (float,int) and math.isfinite(value) and -1<=value<=1099511627776:return {'value':value}
 return {'status':'outside-approved-display-domain'}
def marked(tree,path):
 for part in path.split('.'):
  if tree is True:return True
  if not isinstance(tree,dict):return False
  tree=tree.get(part,False)
 return tree is True

# AzAPI 2.13.0 local provider schema: only these attribute names may be displayed.
PROVIDER_COMPUTED={'id','location','name','output','parent_id','tags','ignore_casing','ignore_missing_property','ignore_null_property','schema_validation_enabled'}
PROVIDER_INPUT={'create_headers','create_query_parameters','delete_headers','delete_query_parameters','ignore_body_changes','ignore_other_items_in_list','list_unique_id_property','locks','read_headers','read_query_parameters','replace_triggers_external_values','replace_triggers_refs','response_export_values','retry','sensitive_body','sensitive_body_version','type','update_headers','update_query_parameters','identity','timeouts'}
SQL_PROPERTIES=set("autoPauseDelay availabilityZone catalogCollation collation createMode elasticPoolId encryptionProtector encryptionProtectorAutoRotation federatedClientId freeLimitExhaustionBehavior highAvailabilityReplicaCount isLedgerOn keys licenseType longTermRetentionBackupResourceId maintenanceConfigurationId manualCutover maxSizeBytes minCapacity performCutover preferredEnclaveType readScale recoverableDatabaseId recoveryServicesRecoveryPointId requestedBackupStorageRedundancy restorableDroppedDatabaseId restorePointInTime sampleName secondaryType sourceDatabaseDeletionDate sourceDatabaseId sourceResourceId useFreeLimit zoneRedundant status databaseId creationDate currentServiceObjectiveName requestedServiceObjectiveName defaultSecondaryLocation maxLogSizeBytes isInfraEncryptionEnabled earliestRestoreDate currentSku currentBackupStorageRedundancy pausedDate resumedDate maintenanceConfigurationId isZoneRedundant maintenanceConfigurationName".split())
BODY_PATHS={'body.'+k for k in ('kind','location','name','id','type','identity','tags')}
BODY_PATHS|={'body.sku.'+k for k in ('name','tier','family','capacity','size')}
BODY_PATHS|={'body.properties.'+k for k in SQL_PROPERTIES}
BODY_PATHS|={'body.properties.currentSku.'+k for k in ('name','tier','family','capacity','size')}

def state_label(value,unknown,sensitive):
 if sensitive:return 'sensitive-withheld'
 if unknown:return 'unknown'
 if value is MISSING:return 'absent'
 if value is None:return 'null'
 return {dict:'object',list:'array',str:'string',bool:'boolean',int:'number',float:'number'}.get(type(value),'invalid')

def other_changes(c,before,after):
 paths=(PROVIDER_COMPUTED|PROVIDER_INPUT)|BODY_PATHS
 rows=[]
 for path in sorted(paths-set(FIELDS)):
  b=value_at(before,path);a=value_at(after,path)
  unknown=marked(c.get('after_unknown',{}),path)
  if type(b) is not type(a) or b!=a or unknown:
   rows.append({'field':path,'classification':'provider_computed' if path in PROVIDER_COMPUTED else 'sql_body' if path.startswith('body.') else 'provider_input',
    'before_status':state_label(b,False,marked(c.get('before_sensitive',{}),path)),
    'after_status':state_label(a,unknown,marked(c.get('after_sensitive',{}),path))})
 # Detect changes outside named schema without revealing arbitrary keys or values.
 def strip_known(obj):
  obj=copy.deepcopy(obj)
  for path in sorted(paths|set(FIELDS),key=len,reverse=True):
   parts=path.split('.');node=obj
   for part in parts[:-1]:
    if not isinstance(node,dict):break
    node=node.get(part)
   if isinstance(node,dict):node.pop(parts[-1],None)
  def prune(v):
   if isinstance(v,dict):return {k:prune(x) for k,x in v.items() if x!={}}
   return v
  return prune(obj)
 return {'classified_changes':rows,'unlisted_fields_changed':strip_known(before)!=strip_known(after)}

def project(plan):
 rows=[r for r in plan.get('resource_changes',[]) if r.get('address')==ADDRESS]
 if len(rows)!=1:raise ValueError('SQL_RESOURCE_COUNT')
 c=rows[0]['change'];before=c.get('before') or {};after=c.get('after') or {}
 actions=c.get('actions')
 if actions not in (['no-op'],['update'],['create'],['delete'],['delete','create'],['create','delete']):actions=['unrecognized']
 changes=[]
 for path in FIELDS:
  b=value_at(before,path);a=value_at(after,path);unknown=marked(c.get('after_unknown',{}),path)
  if type(b) is not type(a) or b!=a or unknown:
   changes.append({'field':path,'before':safe_value(path,b,sensitive=marked(c.get('before_sensitive',{}),path)), 'after':safe_value(path,a,unknown,marked(c.get('after_sensitive',{}),path))})
 def remaining(obj):
  obj=copy.deepcopy(obj)
  for path in FIELDS:
   parts=path.split('.');node=obj
   for part in parts[:-1]:
    if not isinstance(node,dict):break
    node=node.get(part)
   if isinstance(node,dict):node.pop(parts[-1],None)
  return obj
 other_changed=remaining(before)!=remaining(after)
 # Only fixed field paths are printed. Neither arbitrary paths nor raw objects are emitted.
 return {'resource':'sql_database','actions':actions,'changed_cost_security_fields':changes,'other_fields_changed':other_changed,'other_field_diagnostics':other_changes(c,before,after)}
if __name__=='__main__':
 import sys
 try:print('SQL_PLAN_PROJECTION '+json.dumps(project(json.loads(Path(sys.argv[1]).read_text())),sort_keys=True))
 except Exception:raise SystemExit('SQL_PLAN_PROJECTION_FAILED; private values withheld')
