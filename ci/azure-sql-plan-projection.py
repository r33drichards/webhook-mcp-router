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
 return {'resource':'sql_database','actions':actions,'changed_cost_security_fields':changes,'other_fields_changed':other_changed}
if __name__=='__main__':
 import sys
 try:print('SQL_PLAN_PROJECTION '+json.dumps(project(json.loads(Path(sys.argv[1]).read_text())),sort_keys=True))
 except Exception:raise SystemExit('SQL_PLAN_PROJECTION_FAILED; private values withheld')
