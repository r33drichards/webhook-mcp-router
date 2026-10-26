"""Proposed exact-server network window. Separate approval/bootstrap required.
Never changes database SKU, SQL users, runtime app or unrelated firewall rules.
"""
import shutil,time
import ipaddress,json,os,re,subprocess,sys
from pathlib import Path
SERVER='/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-v2/providers/Microsoft.Sql/servers/sql-webhook-mcp-router-v2-f7076f8e38'
STAGE='arguments'
class ArmFailure(ValueError):
 def __init__(self, stderr):
  allowed={'AuthorizationFailed','InvalidAuthenticationToken','ExpiredAuthenticationToken','InvalidRequestContent','BadRequest','ResourceNotFound','ConflictingServerOperation','OperationTimedOut','TooManyRequests'}
  match=re.search(r'\(([A-Za-z][A-Za-z0-9]{0,63})\)',stderr or '')
  self.code=match.group(1) if match and match.group(1) in allowed else 'UNCLASSIFIED'
  super().__init__('ARM_COMMAND_FAILED')
def diagnostic(error):
 category='ARM:'+error.code if isinstance(error,ArmFailure) else {FileNotFoundError:'CLI_NOT_FOUND',subprocess.TimeoutExpired:'CLI_TIMEOUT',ValueError:'CONTRACT_OR_FORMAT',KeyError:'RESPONSE_SHAPE'}.get(type(error),'OTHER')
 print('SQL_WINDOW_DIAGNOSTIC stage='+STAGE+' category='+category,file=sys.stderr)
def closed_readback():
 global STAGE
 STAGE='close_readback'
 last=None
 for attempt in range(6):
  try:
   state=rest('get',SERVER)['properties']['publicNetworkAccess']
   if state=='Disabled':
    print('SQL_WINDOW_READBACK pna=Disabled',file=sys.stderr);return
   last=ValueError('PNA_NOT_DISABLED')
  except Exception as error:last=error
  if attempt<5:time.sleep(2)
 raise last

def require(value):
 if not value:raise ValueError('NETWORK_WINDOW_CONTRACT')
def rule_name():
 run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];require(bool(re.fullmatch('[0-9]{1,20}',run)) and bool(re.fullmatch('[0-9]{1,4}',attempt)))
 return 'router-migration-'+run+'-'+attempt
def rest(method,path,body=None):
 executable=shutil.which('az')
 if not executable:raise FileNotFoundError('AZURE_CLI_NOT_FOUND')
 args=[executable,'rest','--method',method,'--url','https://management.azure.com'+path+('?api-version=2023-08-01'),'--only-show-errors','--output','json']
 if body is not None:args+=['--body',json.dumps(body,separators=(',',':'))]
 result=subprocess.run(args,capture_output=True,text=True,timeout=120)
 if result.returncode!=0:raise ArmFailure(result.stderr)
 return json.loads(result.stdout) if result.stdout.strip() else {}
def public_ip(value):
 ip=ipaddress.ip_address(value);require(ip.version==4 and ip.is_global);return str(ip)
def rules():return rest('get',SERVER+'/firewallRules')['value']
def operation(mode,probe=None):
 global STAGE
 STAGE="preflight"
 name=rule_name();path=SERVER+'/firewallRules/'+name
 if mode=='open':
  require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Disabled' and rules()==[])
  if os.environ.get('SQL_WINDOW_MARKER'):Path(os.environ['SQL_WINDOW_MARKER']).write_text(name)
  STAGE='open_request'
  rest('patch',SERVER,{'properties':{'publicNetworkAccess':'Enabled'}})
  STAGE='open_readback'
  require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled' and rules()==[])
 elif mode=='allow':
  require(probe.get('sqlError')==40615 and set(probe)=={'sqlError','serverObservedTdsIpv4'})
  ip=public_ip(probe['serverObservedTdsIpv4']);require(rules()==[] and rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled')
  STAGE='rule_create'
  rest('put',path,{'properties':{'startIpAddress':ip,'endIpAddress':ip}})
  actual=rules();require(len(actual)==1 and actual[0]['name']==name and actual[0]['properties']['startIpAddress']==ip and actual[0]['properties']['endIpAddress']==ip)
 elif mode=='cleanup':
  # Azure forbids firewall edits while PNA is Disabled. Never reopen implicitly.
  # Delete the owned rule while enabled, then close in finally even on failure.
  try:
   STAGE='cleanup_rule_read'
   actual=rules();owned=any(r['name']==name for r in actual)
   if owned:
    require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled')
    STAGE='cleanup_rule_delete'
    rest('delete',path)
    require(not any(r['name']==name for r in rules()))
  except Exception as error:
   diagnostic(error);raise
  finally:
   STAGE='close_request'
   try:
    rest('patch',SERVER,{'properties':{'publicNetworkAccess':'Disabled'}})
   except Exception as error:
    diagnostic(error);raise
   finally:
    # Read back even if the request failed/timed out; repeat GET only, never PATCH.
    closed_readback()
  STAGE='cleanup_rule_readback'
  require(not any(r['name']==name for r in rules()))
  print('SQL_WINDOW_READBACK owned_rule_absent=true',file=sys.stderr)
 else:raise ValueError('UNKNOWN_MODE')
if __name__=='__main__':
 try:
  mode=sys.argv[1];probe=json.load(open(sys.argv[2])) if mode=='allow' else None
  operation(mode,probe);print('PASS SQL_NETWORK_WINDOW_'+mode.upper())
 except Exception as error:
  diagnostic(error)
  raise SystemExit('SQL_NETWORK_WINDOW_FAILED; details withheld; operator must verify closed network')
