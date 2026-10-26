"""Bounded failure diagnostics and closure readback; no Azure requests."""
import contextlib,importlib.util,io,os
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('window',root/'azure-sql-migration-window.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
count=0
with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','SQL_WINDOW_MARKER':''}),patch.object(m.time,'sleep'):
 for scenario in ['normal','delayed','transient_get','patch_failed_closed','patch_failed_open','readback_denied']:
  calls=[];reads=0;patched=False
  def fake(method,path,body=None):
   global reads,patched
   calls.append((method,path,body))
   if path.endswith('/firewallRules'):return {'value':[]}
   if method=='patch':
    patched=True
    if scenario.startswith('patch_failed'):raise m.ArmFailure('ERROR: (BadRequest) SECRET')
    return {}
   assert method=='get' and patched
   reads+=1
   if scenario=='readback_denied' or (scenario=='transient_get' and reads==1):raise m.ArmFailure('ERROR: (AuthorizationFailed) SECRET')
   value='Enabled' if scenario=='patch_failed_open' or (scenario=='delayed' and reads<3) else 'Disabled'
   return {'properties':{'publicNetworkAccess':value}}
  m.rest=fake;output=io.StringIO();failed=False
  with contextlib.redirect_stderr(output):
   try:m.operation('cleanup')
   except ValueError:failed=True
  assert failed==(scenario in ['patch_failed_closed','patch_failed_open','readback_denied'])
  assert reads==(24 if scenario in ['patch_failed_open','readback_denied'] else 3 if scenario=='delayed' else 2 if scenario=='transient_get' else 1)
  assert sum(c[0]=='patch' for c in calls)==1
  assert all(c[2]['properties']['publicNetworkAccess']=='Disabled' for c in calls if c[0]=='patch')
  assert 'SECRET' not in output.getvalue()
  assert ('pna=Disabled' in output.getvalue())==(scenario not in ['patch_failed_open','readback_denied'])
  count+=1
 for raw,expected in [('ERROR: (AuthorizationFailed) SECRET','ARM:AuthorizationFailed'),('ERROR: (UntrustedPayload) SECRET','ARM:UNCLASSIFIED'),('SECRET','ARM:UNCLASSIFIED')]:
  output=io.StringIO()
  with contextlib.redirect_stderr(output):m.diagnostic(m.ArmFailure(raw))
  assert expected in output.getvalue() and 'SECRET' not in output.getvalue() and 'UntrustedPayload' not in output.getvalue();count+=1
source=(root.parent/'tools/Router.Migrator/Program.cs').read_text();failure=source.split('} catch(Exception error) {',1)[1]
assert 'Console.Error.WriteLine' in failure and 'Take(4)' in failure
assert 'number=e.Number,state=e.State,severity=e.Class' in failure
for forbidden in ['error.Message','error.ToString','access.Token','ConnectionString','StackTrace']:
 assert forbidden not in failure
assert 'stage="SQL_TOKEN_ACQUISITION"' in source and 'stage="TDS_PROBE_CONNECT"' in source
print(f'PASS {count} bounded cleanup/ARM diagnostic cases plus stderr numeric-only probe contract')

# Enabling is asynchronous: retry only observation, never the enabling PATCH.
with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','SQL_WINDOW_MARKER':''}),patch.object(m.time,'sleep'):
 for scenario in ['immediate','delayed','never','foreign_rule','unknown']:
  calls=[];observations=0;opened=False
  def fake_open(method,path,body=None):
   global observations,opened
   calls.append((method,path,body))
   if method=='patch':opened=True;return {}
   if path.endswith('/firewallRules'):
    return {'value':[{'name':'unrelated'}] if opened and scenario=='foreign_rule' else []}
   if not opened:return {'properties':{'publicNetworkAccess':'Disabled'}}
   observations+=1
   state='UNKNOWN' if scenario=='unknown' else 'Disabled' if scenario=='never' or scenario=='delayed' and observations<3 else 'Enabled'
   return {'properties':{'publicNetworkAccess':state}}
  m.rest=fake_open;failed=False;output=io.StringIO()
  with contextlib.redirect_stderr(output):
   try:m.operation('open')
   except ValueError:failed=True
  assert failed==(scenario in ['never','foreign_rule','unknown'])
  assert sum(c[0]=='patch' for c in calls)==1
  assert observations==(6 if scenario=='never' else 3 if scenario=='delayed' else 1)
  assert 'unrelated' not in output.getvalue()
print('PASS 5 bounded open-readback cases; foreign rules fail immediately; one PATCH only')

# A real monotonic deadline bounds even a slow GET; it resets after failure.
with patch.object(m.time,'monotonic',side_effect=[0,121]),patch.object(m,'rest') as request:
 try:m.closed_readback()
 except ValueError:pass
 else:raise AssertionError('Elapsed deadline accepted')
 request.assert_not_called();assert m.READBACK_DEADLINE is None
# The connection retry wraps only opening connections, never Migration.Run.
program=(root.parent/'tools/Router.Migrator/Program.cs').read_text()
warmup=(root.parent/'tools/Router.Migrator/ConnectionWarmup.cs').read_text()
assert program.count('Migration.Run(Connect,scripts)')==1
assert program.index('stage="PRE_MIGRATION_CONNECT"') < program.index('stage="MIGRATION_TRANSACTION"')
assert 'ConnectRetryCount=0' in program
assert 'Migration.Run' not in warmup and 'OpenAsync(ct)' in warmup
assert 'TimeSpan.FromMinutes(2)' in warmup and 'attempt<6' in warmup
print('PASS elapsed readback deadline and no transaction-replay source boundary')
