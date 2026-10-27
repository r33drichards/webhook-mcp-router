import copy, importlib.util, runpy
from pathlib import Path
root=Path(__file__).parent
fixtures=runpy.run_path(str(root/'test-azure-public-mcp-plan-check.py'))
spec=importlib.util.spec_from_file_location('update',root/'azure-package-update-plan-check.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=copy.deepcopy(fixtures['noop'])
c=p['resource_changes'][-1]['change'];c['actions']=['update']
def package(value,digest):
    next(s for s in value['body']['properties']['siteConfig']['appSettings'] if s['name']=='WEBSITE_RUN_FROM_PACKAGE')['value']=m.PREFIX+digest+'.zip'
package(c['after'],m.NEW)
assert m.validate(p)==13
noop=copy.deepcopy(p);nc=noop['resource_changes'][-1]['change'];nc['before']=copy.deepcopy(nc['after']);nc['actions']=['no-op']
assert m.validate(noop,True)==13
cases=[]
# Carry forward every hostile activation fixture, retaining a valid package update.
for original in fixtures['cases']:
    x=copy.deepcopy(original)
    rows=[r for r in x['resource_changes'] if r['address']==m.APP]
    if len(rows)==1:
        d=rows[0]['change']
        d['before']=copy.deepcopy(c['before'])
        try:package(d['after'],m.NEW)
        except (KeyError,TypeError,StopIteration):pass
    # A package substitution itself is permitted here, so omit only that old test.
    if original['resource_changes'][-1]['change'].get('after',{}).get('body',{}).get('properties',{}).get('siteConfig',{}).get('appSettings'):
        entries=original['resource_changes'][-1]['change']['after']['body']['properties']['siteConfig']['appSettings']
        if any(e.get('name')=='WEBSITE_RUN_FROM_PACKAGE' and e.get('value')=='unapproved' for e in entries):continue
    cases.append(x)
for side in ('before','after'):
    for digest in ('0'*64,'../unapproved',m.NEW if side=='before' else m.OLD):
        x=copy.deepcopy(p);package(x['resource_changes'][-1]['change'][side],digest);cases.append(x)
for side in ('before','after'):
    x=copy.deepcopy(p);x['resource_changes'][-1]['change'][side]['body']['properties']['enabled']=False;cases.append(x)
    x=copy.deepcopy(p);x['resource_changes'][-1]['change'][side]['body']['properties']['siteConfig']['appSettings'].append({'name':'WEBSITE_RUN_FROM_PACKAGE','value':m.PREFIX+m.NEW+'.zip'});cases.append(x)
x=copy.deepcopy(p);x['resource_changes'][-1]['change']['before']['tags']={'unapproved':'removed'};cases.append(x)
for i,x in enumerate(cases):
    try:m.validate(x)
    except (ValueError,KeyError,TypeError):pass
    else:raise AssertionError(f'Unsafe package change accepted case {i}')
try:m.validate(p,True)
except ValueError:pass
else:raise AssertionError('Postapply update accepted')
print(f'PASS {len(cases)+3} package-only update cases; no cloud changes')
