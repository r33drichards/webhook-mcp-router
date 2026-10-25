import json
import pathlib
import sys

state = json.loads(pathlib.Path('ci/hosted-readiness.json').read_text())
if state.get('ready') is not True:
    print('DEPLOYMENT BLOCKED: ' + '; '.join(state['blockers']))
    sys.exit(1)
for path in ['ci/build-hosted.sh', 'deploy/app.yaml', 'deploy/wasmer.toml']:
    if not pathlib.Path(path).is_file():
        sys.exit('DEPLOYMENT BLOCKED: missing reviewed ' + path)
