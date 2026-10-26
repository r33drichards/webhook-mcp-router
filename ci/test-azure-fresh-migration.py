import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'deploy/azure/runtime/migration-plan.py'
s=importlib.util.spec_from_file_location('migration',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class DB:
    def __init__(self, existing=(), fail=None):
        self.autocommit=False; self.existing=existing; self.fail=fail; self.queries=[]; self.committed=False; self.rolled=False; self.reads=0
    def cursor(self): return self
    def execute(self, sql):
        self.queries.append(sql)
        if sql.startswith('SELECT SCHEMA_NAME'):
            self.reads+=1
            return [(x,) for x in (self.existing if self.reads==1 else m.TABLES)]
        if self.fail and self.fail in sql: raise ValueError('synthetic failure')
        return self
    def commit(self): self.committed=True
    def rollback(self): self.rolled=True
ok=DB();m.apply_fresh(ok,'synthetic grants');assert ok.committed and not ok.rolled
assert len(ok.queries)==5
for db in [DB(existing=['registry.Policies']),DB(existing=['unrelated.Table']),DB(fail='CREATE TABLE registry.Subscriptions'),DB(fail='CREATE TABLE registry.Destinations'),DB(fail='synthetic grants')]:
    try:m.apply_fresh(db,'synthetic grants')
    except ValueError:pass
    else:raise AssertionError('Unsafe migration passed')
    assert not db.committed and db.rolled
bad=DB();bad.autocommit=True
try:m.apply_fresh(bad,'synthetic grants')
except ValueError:pass
else:raise AssertionError('Autocommit accepted')
assert not bad.queries
assert len(m.manifest())==2
print('PASS 8 fresh-migration orchestration checks (mock DB, not SQL execution)')
