"""Permit only the reviewed package URL change on the already public MCP app."""
import copy
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('public', Path(__file__).with_name('azure-public-mcp-plan-check.py'))
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)
APP = public.APP
OLD = '569149d7e4e242108c1b8d7d67de6c0f8e420f0fa1d7cf596e0cc41802ce67d8'
# Exact scope-upgrade package digest verified from build 40483488868.
NEW = '4375b7c0546a524339a0698d0e86fb23727c7af3c7d1c257b45fe19a95d9ef35'
PREFIX = 'https://whmcprv2f7076f8e38.blob.core.windows.net/router-packages/'

def validate(plan, require_noop=False):
    public.closed.reject_write_only(plan)
    rows = plan.get('resource_changes', [])
    apps = [r for r in rows if r.get('address') == APP]
    if len(apps) != 1: raise ValueError('APP_REQUIRED')
    c = apps[0]['change']
    actions = c['actions']
    if actions not in (['update'], ['no-op']): raise ValueError('EXISTING_APP_ONLY')
    if require_noop and any(r['change']['actions'] != ['no-op'] for r in rows): raise ValueError('POST_APPLY_DRIFT')
    unknown = copy.deepcopy(c.get('after_unknown', {}))
    if not isinstance(unknown, dict): raise ValueError('UNKNOWN_INPUT')
    unknown.pop('output', None)
    if public.present(unknown): raise ValueError('UNKNOWN_INPUT')
    snapshots = []
    for side, digest in (('before', NEW if actions == ['no-op'] else OLD), ('after', NEW)):
        value = public.project(c[side], public=True)
        settings = value['body']['properties']['siteConfig']['appSettings']
        packages = [e for e in settings if e.get('name') == 'WEBSITE_RUN_FROM_PACKAGE']
        if len(packages) != 1 or packages[0].get('value') != PREFIX + digest + '.zip': raise ValueError('PACKAGE_PIN')
        packages[0]['value'] = PREFIX + OLD + '.zip'
        snapshots.append(value)
        projected = copy.deepcopy(plan)
        row = next(r for r in projected['resource_changes'] if r['address'] == APP)
        row['change']['actions'] = ['no-op']
        row['change']['after'] = value
        if public.closed.validate(projected, OLD) != 13: raise ValueError('INVENTORY')
    for s in snapshots: s.pop('output', None)
    if not public.closed.base.exact(*snapshots): raise ValueError('UNAPPROVED_APP_DELTA')
    if any(c.get('actions') != ['no-op'] for c in plan.get('output_changes', {}).values()): raise ValueError('OUTPUT_CHANGE')
    return 13

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('plan'); p.add_argument('--require-noop', action='store_true')
    args = p.parse_args()
    try:
        validate(json.loads(Path(args.plan).read_text()), args.require_noop)
        print('PASS package-only public MCP update; resources=13; SQL closed; dispatch disabled')
    except Exception:
        raise SystemExit('FAIL PACKAGE_UPDATE_PLAN_REJECTED')
