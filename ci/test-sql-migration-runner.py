"""Offline regression checks plus optional installed Azure CLI version probe.
No login, token acquisition, Azure API calls or credentials in this test.
"""
import importlib.util,json,os,runpy,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).parent
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,root/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('deploy','azure-disabled-app-deploy.py');w=load('window','azure-sql-migration-window.py')
with tempfile.TemporaryDirectory() as tmp:
 marker=Path(tmp)/'live-marker'
 for existing in (False,True):
  if existing:marker.write_text('real-job-marker-do-not-touch')
  with patch.dict(os.environ,{'SQL_WINDOW_MARKER':str(marker),'GITHUB_RUN_ID':'987','GITHUB_RUN_ATTEMPT':'4'}):
   runpy.run_path(str(root/'test-azure-sql-migration-window.py'),run_name='__main__')
   assert os.environ['GITHUB_RUN_ID']=='987' and os.environ['GITHUB_RUN_ATTEMPT']=='4'
   assert os.environ['SQL_WINDOW_MARKER']==str(marker)
   assert marker.exists()==existing
   if existing:assert marker.read_text()=='real-job-marker-do-not-touch'
print('PASS offline test preserves absent/existing live marker and runner environment')
for module,invoke in [(m,lambda:m.az('version')),(w,lambda:w.rest('get',w.SERVER))]:
 with patch.object(module.shutil,'which',return_value=r'C:\Program Files\Azure CLI\az.cmd'),patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'{}',b'')) as call:
  invoke();assert call.call_args.args[0][0]==r'C:\Program Files\Azure CLI\az.cmd'
  assert not call.call_args.kwargs.get('shell',False)
 with patch.object(module.shutil,'which',return_value=None),patch.object(module.subprocess,'run') as call:
  try:invoke()
  except FileNotFoundError:pass
  else:raise AssertionError('Missing CLI not rejected')
  call.assert_not_called()
print('PASS both Azure CLI callers resolve Windows executable and fail closed if absent')
for error,expected in [(FileNotFoundError('PRIVATE'), 'EXECUTABLE_NOT_FOUND'),(subprocess.TimeoutExpired(['SECRET'],1,output='TOKEN'),'PROCESS_TIMEOUT'),(KeyError('TOKEN'),'CONFIG_MISSING'),(ValueError('SECRET'),'CONTRACT_OR_FORMAT'),(OSError('TOKEN'),'OS_ERROR'),(RuntimeError('SECRET'),'OTHER_ERROR'),(m.CliFailed(b'private AADSTS530035 token=SECRET'),'CLI_EXIT_NONZERO:AADSTS530035'),(m.CliFailed(b'SECRET\nmalicious output'),'CLI_EXIT_NONZERO')]:
 assert m.safe_error(error)==expected
print('PASS 8 diagnostic cases disclose only fixed categories and numeric AADSTS codes')
# Current explicit stage assignments are a fixed allowlist, not exception/config text.
source=(root/'azure-disabled-app-deploy.py').read_text()
import re
assert set(re.findall(r"LOGIN_STAGE='([^']+)'",source))=={'not_started','config','isolated_cache','github_token','github_claims','azure_exchange','subscription_select','account_read','arm_token','azure_claims'}
if '--installed-cli' in sys.argv:
 # Invoke the exact production wrapper on Windows without authentication.
 version=json.loads(m.az('version'))
 assert isinstance(version.get('azure-cli'),str)
 print('PASS installed Azure CLI resolved invocation version='+version['azure-cli'])
