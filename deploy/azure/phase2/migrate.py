#!/usr/bin/env python3
"""Explicit migration using operator's existing az login. No token printing/persistence.
Requires approved exact operator firewall rule, ODBC Driver 18 and pyodbc.
Run only against the dedicated router database after verifying identity and schema.
"""
import argparse,json,pathlib,re,struct,subprocess
p=argparse.ArgumentParser()
p.add_argument('--server',required=True); p.add_argument('--subscription',required=True)
p.add_argument('--schema',type=pathlib.Path,required=True);p.add_argument('--grants',type=pathlib.Path,required=True)
p.add_argument('--generic',action='store_true',help='Fresh-only baseline and destination schema in one transaction')
a=p.parse_args()
if not re.fullmatch(r'[a-z0-9-]+\.database\.windows\.net',a.server): p.error('Invalid Azure SQL FQDN')
if a.generic:
 import importlib.util
 module_path=pathlib.Path(__file__).resolve().parents[1]/'runtime/migration-plan.py'
 spec=importlib.util.spec_from_file_location('router_migration',module_path)
 migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
 if a.schema.resolve() != (migration.ROOT/migration.SCHEMAS[0]).resolve(): p.error('Generic migration requires the pinned repository baseline schema')
import pyodbc
# Standard access-token exchange under the operator's existing authorized session.
result=subprocess.run(['az','account','get-access-token','--subscription',a.subscription,'--resource','https://database.windows.net/','--output','json','--only-show-errors'],capture_output=True,text=True,timeout=60)
if result.returncode: raise SystemExit('Azure SQL token acquisition failed; token/stderr withheld')
try: token=json.loads(result.stdout)['accessToken'].encode('utf-16-le')
except (KeyError,ValueError): raise SystemExit('Invalid token response; response withheld')
packed=struct.pack('<I',len(token))+token
try:
 with pyodbc.connect(f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{a.server},1433;Database=router;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;',attrs_before={1256:packed},autocommit=False) as db:
  if a.generic:
   migration.apply_fresh(db,a.grants.read_text())
  else:
   tables=set(row[0] for row in db.cursor().execute("SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0"))
   if tables: raise RuntimeError('Nonempty database requires reviewed migration')
   db.cursor().execute(a.schema.read_text())
   db.cursor().execute(a.grants.read_text())
   db.commit()
 print('Router schema and scoped grants applied; no token output')
except Exception:
 raise SystemExit('SQL migration failed; inspect securely as operator (details withheld)')
finally:
 token=b'';packed=b'';result=None
