"""Fail closed: exact verified inventory, complete no-mutation adoption plan."""
import json
import sys
from pathlib import Path
INVENTORY = Path(__file__).resolve().parents[1] / 'deploy/azure/terraform/inventory.auto.tfvars.json'

def validate(plan):
    expected = json.loads(INVENTORY.read_text())['existing']
    if plan.get('format_version') != '1.2' or plan.get('terraform_version') != '1.15.8':
        raise ValueError('UNREVIEWED_PLAN_VERSION')
    if plan.get('complete') is not True or plan.get('errored') is not False or plan.get('deferred_changes'):
        raise ValueError('INCOMPLETE_PLAN')
    for field in ('action_invocations', 'deferred_action_invocations'):
        if field in plan and plan[field] != []:
            raise ValueError('ACTION_INVOCATIONS_NOT_ALLOWED')
    seen = set()
    for resource in plan.get('resource_changes', []):
        key = resource.get('index')
        if (resource.get('mode') != 'managed' or resource.get('type') != 'azapi_resource'
                or resource.get('name') != 'existing' or key not in expected or key in seen
                or resource.get('address') != 'azapi_resource.existing[' + json.dumps(key) + ']'):
            raise ValueError('UNEXPECTED_RESOURCE')
        seen.add(key)
        change = resource.get('change', {})
        if change.get('actions') != ['no-op']:
            raise ValueError('MUTATION_NOT_ALLOWED')
        item = expected[key]
        after = change.get('after') or {}
        importing = change.get('importing')
        rid = importing.get('id') if importing else after.get('id')
        if not isinstance(rid, str):
            raise ValueError('MISSING_ID')
        base, separator, query = rid.partition('?')
        if base.lower() != item['id'].lower():
            raise ValueError('RESOURCE_SCOPE_MISMATCH')
        if separator and query != 'api-version=' + item['type'].split('@')[1]:
            raise ValueError('API_VERSION_MISMATCH')
        if importing and not separator:
            raise ValueError('UNPINNED_IMPORT')
        if after.get('type') != item['type']:
            raise ValueError('RESOURCE_TYPE_MISMATCH')
    if seen != set(expected):
        raise ValueError('INCOMPLETE_INVENTORY')
    for output in plan.get('output_changes', {}).values():
        if output.get('actions') != ['no-op']:
            raise ValueError('OUTPUT_CHANGE_NOT_ALLOWED')
    return len(seen)

if __name__ == '__main__':
    try:
        count = validate(json.loads(Path(sys.argv[1]).read_text()))
        print('PASS import-only plan guard; resources=' + str(count))
    except Exception:
        print('FAIL import-only plan guard; details withheld')
        raise SystemExit(1)
