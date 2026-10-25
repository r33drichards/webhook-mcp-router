"""Assert embedded Go OPA evaluator behavior inside Wasmer, not OPA's Wasm ABI."""
import json
import subprocess
import sys

wasm = sys.argv[1]
base = dict(event=dict(type='pull_request', action='opened', repository='synthetic/repo'),
            subscriptions=[dict(id='sub_match', repository='synthetic/repo'),
                           dict(id='sub_other', repository='synthetic/other')])
for action, expected in [('opened', ['sub_match']), ('closed', [])]:
    base['event']['action'] = action
    result = subprocess.run(['wasmer', 'run', wasm], input=json.dumps(base),
                            text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, 'embedded OPA guest failed'
    assert json.loads(result.stdout) == expected
bad = subprocess.run(['wasmer', 'run', wasm], input='{', text=True,
                     capture_output=True, timeout=45)
assert bad.returncode != 0
print('PASS: embedded native Go OPA library under Wasmer, match/nonmatch/malformed input')
