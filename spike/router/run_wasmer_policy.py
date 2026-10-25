"""Reproduce compiled OPA-on-Wasmer checks. All inputs are synthetic/local."""
import json, os, pathlib, subprocess
root=pathlib.Path(__file__).resolve().parents[2]
log=root/'docs/runtime-logs/opa-wasmer-evidence.json'
env=dict(os.environ, WASMER_DIR=str(root/'.tools/wasmer'))
records=[]
def run(args, data=None, expected_code=0):
    result=subprocess.run(args,cwd=root,env=env,input=data,text=True,capture_output=True,timeout=30)
    records.append({'command':args,'stdin':data,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    log.write_text(json.dumps(records,indent=2)+'\n')
    assert result.returncode==expected_code, records[-1]
    return result.stdout
run(['.tools/wasmer/bin/wasmer','--version'])
run(['.tools/opa','version'])
run(['.tools/opa','build','--capabilities','policies/capabilities.json','-t','wasm','-e','router/subscription_ids','-o','spike/router/policy.tar.gz','policies/routes.rego'])
run(['tar','-xzf','spike/router/policy.tar.gz','-C','spike/router'])
run(['cc','-Wall','-Wextra','-Werror','-I.tools/wasmer/include','spike/router/wasmer_opa_host.c','-L.tools/wasmer/lib','-lwasmer','-Wl,-rpath,'+str(root/'.tools/wasmer/lib'),'-o','spike/router/wasmer-opa-host'])
for fixture, expected in [('wasm-matching.json',['sub_match']),('wasm-nonmatching.json',[])]:
    raw=(root/'spike/router'/fixture).read_text()
    output=run(['spike/router/wasmer-opa-host','spike/router/policy.wasm'],raw)
    assert json.loads(output)==[{'result':expected}], output
    native=json.loads(run(['.tools/opa','eval','--stdin-input','--data','policies/routes.rego','data.router.subscription_ids'],raw))
    assert native['result'][0]['expressions'][0]['value']==expected
run(['spike/router/wasmer-opa-host','spike/router/policy.wasm'],'not-json',1)
print('PASS: Wasmer guest match/nonmatch, native decision parity, malformed JSON rejection; evidence:',log)
