import importlib.util
import copy
import json
from pathlib import Path
spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('azure-import-plan-check.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
items = json.loads(m.INVENTORY.read_text())['existing']
good = {'format_version': '1.2', 'terraform_version': '1.15.8', 'complete': True, 'errored': False, 'resource_changes': [{'address': 'azapi_resource.existing[' + json.dumps(k) + ']', 'index': k, 'mode': 'managed', 'type': 'azapi_resource', 'name': 'existing', 'change': {'actions': ['no-op'], 'importing': {'id': v['id'] + '?api-version=' + v['type'].split('@')[1]}, 'after': {'id': v['id'], 'type': v['type']}}} for k, v in items.items()]}
assert m.validate(good) == 12
existing = copy.deepcopy(good)
for r in existing['resource_changes']: del r['change']['importing']
assert m.validate(existing) == 12
bad = []
def mutate(fn):
    p = copy.deepcopy(good); fn(p); bad.append(p)
for actions in [['create'], ['update'], ['delete'], ['delete', 'create'], ['read']]:
    mutate(lambda p: p['resource_changes'][0]['change'].update(actions=actions))
for field, value in [('errored', True), ('deferred_changes', [{}]), ('complete', False)]:
    mutate(lambda p: p.update({field: value}))
mutate(lambda p: p['resource_changes'].pop())
mutate(lambda p: p['resource_changes'].append(copy.deepcopy(p['resource_changes'][0])))
mutate(lambda p: p['resource_changes'][0].update(address='module.other.azapi_resource.existing["group"]'))
mutate(lambda p: p['resource_changes'][0]['change']['importing'].update(id='/subscriptions/other/resourceGroups/other'))
mutate(lambda p: p['resource_changes'][0]['change']['after'].update(type='Microsoft.Web/sites@2024-04-01'))
mutate(lambda p: p['resource_changes'][0]['change']['importing'].update(id=items['group']['id']))
mutate(lambda p: p['resource_changes'][0]['change']['importing'].update(id=items['group']['id']+'?api-version=1900-01-01'))
mutate(lambda p: next(r for r in p['resource_changes'] if r['index']=='sql_database')['change']['importing'].update(id=items['sql_server']['id']+'/databases/master?api-version=2023-08-01'))
mutate(lambda p: p.update(output_changes={'private': {'actions': ['create']}}))
for field in ['format_version', 'terraform_version', 'complete', 'errored']:
    mutate(lambda p: p.pop(field))
for field, value in [('format_version', '1.3'), ('terraform_version', '1.15.9'), ('complete', 1), ('complete', 'true'), ('errored', 0)]:
    mutate(lambda p: p.update({field: value}))
for field in ['action_invocations', 'deferred_action_invocations']:
    for value in [[{}], None, {}, 'unexpected']:
        mutate(lambda p: p.update({field: value}))
    empty = copy.deepcopy(good); empty[field] = []; assert m.validate(empty) == 12
bad.append({'resource_changes': []})
for p in bad:
    try: m.validate(p)
    except ValueError: continue
    raise AssertionError('Unsafe plan accepted')
print(f'PASS {len(bad)+4} import-plan guard cases')
