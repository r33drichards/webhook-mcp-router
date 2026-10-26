import importlib.util,copy,json
from pathlib import Path
s=importlib.util.spec_from_file_location('projection',Path(__file__).with_name('azure-sql-plan-projection.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
before={'body':{'sku':{'name':'GP_S_Gen5','capacity':2},'properties':{'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','maxSizeBytes':34359738368}}}
after=copy.deepcopy(before);after['body']['sku']['name']='GP_S_Gen5_2'
p={'resource_changes':[{'address':m.ADDRESS,'change':{'actions':['update'],'before':before,'after':after}}]}
r=m.project(p);assert r['changed_cost_security_fields']==[{'field':'body.sku.name','before':{'value':'GP_S_Gen5'},'after':{'value':'GP_S_Gen5_2'}}]
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after']['body']['password']='DO_NOT_PRINT';q['resource_changes'].append({'address':'secret.DO_NOT_PRINT','change':{'after':{'secret':'DO_NOT_PRINT'}}});assert 'DO_NOT_PRINT' not in json.dumps(m.project(q))
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after']['body']['sku']['name']='DO_NOT_PRINT';assert 'DO_NOT_PRINT' not in json.dumps(m.project(q))
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after_sensitive']={'body':True};assert m.project(q)['changed_cost_security_fields'][0]['after']=={'status':'sensitive-withheld'}
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after_unknown']={'body':{'sku':{'name':True}}};assert m.project(q)['changed_cost_security_fields'][0]['after']=={'status':'unknown'}
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after']['body']['sku']['capacity']=float('inf');assert 'Infinity' not in json.dumps(m.project(q))
q=copy.deepcopy(p);q['resource_changes'][0]['change']['after']=copy.deepcopy(before);assert m.project(q)['changed_cost_security_fields']==[]
print('PASS 7 SQL projection checks; synthetic canonical-SKU fixture, no live plan inspected')
