"""Proposed exact-server network window. Separate approval/bootstrap required.
Never changes database SKU, SQL users, runtime app or unrelated firewall rules.
"""
import ipaddress,json,os,re,subprocess,sys
from pathlib import Path
SERVER='/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-v2/providers/Microsoft.Sql/servers/sql-webhook-mcp-router-v2-f7076f8e38'
def require(value):
 if not value:raise ValueError('NETWORK_WINDOW_CONTRACT')
def rule_name():
 run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];require(bool(re.fullmatch('[0-9]{1,20}',run)) and bool(re.fullmatch('[0-9]{1,4}',attempt)))
 return 'router-migration-'+run+'-'+attempt
def rest(method,path,body=None):
 args=['az','rest','--method',method,'--url','https://management.azure.com'+path+('?api-version=2023-08-01'),'--only-show-errors','--output','json']
 if body is not None:args+=['--body',json.dumps(body,separators=(',',':'))]
 result=subprocess.run(args,capture_output=True,text=True,timeout=120)
 require(result.returncode==0);return json.loads(result.stdout) if result.stdout.strip() else {}
def public_ip(value):
 ip=ipaddress.ip_address(value);require(ip.version==4 and ip.is_global);return str(ip)
def rules():return rest('get',SERVER+'/firewallRules')['value']
def operation(mode,probe=None):
 name=rule_name();path=SERVER+'/firewallRules/'+name
 if mode=='open':
  require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Disabled' and rules()==[])
  if os.environ.get('SQL_WINDOW_MARKER'):Path(os.environ['SQL_WINDOW_MARKER']).write_text(name)
  rest('patch',SERVER,{'properties':{'publicNetworkAccess':'Enabled'}})
  require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled' and rules()==[])
 elif mode=='allow':
  require(probe.get('sqlError')==40615 and set(probe)=={'sqlError','serverObservedTdsIpv4'})
  ip=public_ip(probe['serverObservedTdsIpv4']);require(rules()==[] and rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled')
  rest('put',path,{'properties':{'startIpAddress':ip,'endIpAddress':ip}})
  actual=rules();require(len(actual)==1 and actual[0]['name']==name and actual[0]['properties']['startIpAddress']==ip and actual[0]['properties']['endIpAddress']==ip)
 elif mode=='cleanup':
  # Azure forbids firewall edits while PNA is Disabled. Never reopen implicitly.
  # Delete the owned rule while enabled, then close in finally even on failure.
  try:
   actual=rules();owned=any(r['name']==name for r in actual)
   if owned:
    require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Enabled')
    rest('delete',path)
    require(not any(r['name']==name for r in rules()))
  finally:
   rest('patch',SERVER,{'properties':{'publicNetworkAccess':'Disabled'}})
   require(rest('get',SERVER)['properties']['publicNetworkAccess']=='Disabled')
  require(not any(r['name']==name for r in rules()))
 else:raise ValueError('UNKNOWN_MODE')
if __name__=='__main__':
 try:
  mode=sys.argv[1];probe=json.load(open(sys.argv[2])) if mode=='allow' else None
  operation(mode,probe);print('PASS SQL_NETWORK_WINDOW_'+mode.upper())
 except Exception:raise SystemExit('SQL_NETWORK_WINDOW_FAILED; details withheld; operator must verify closed network')
