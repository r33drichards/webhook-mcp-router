#!/usr/bin/env python3
"""Explicit migration using operator's existing az login. No token printing/persistence.
Requires approved exact operator firewall rule, ODBC Driver 18 and pyodbc.
Run only against the dedicated router database after verifying identity and schema.
"""
import argparse,json,pathlib,re,struct,subprocess
p=argparse.ArgumentParser()
p.add_argument('--server',required=True); p.add_argument('--subscription',required=True)
p.add_argument('--schema',type=pathlib.Path,required=True);p.add_argument('--grants',type=pathlib.Path,required=True)
a=p.parse_args()
if not re.fullmatch(r'[a-z0-9-]+\.database\.windows\.net',a.server): p.error('Invalid Azure SQL FQDN')
import pyodbc
# Standard access-token exchange under the operator's existing authorized session.
result=subprocess.run(['az','account','get-access-token','--subscription',a.subscription,'--resource','https://database.windows.net/','--output','json','--only-show-errors'],capture_output=True,text=True,timeout=60)
if result.returncode: raise SystemExit('Azure SQL token acquisition failed; token/stderr withheld')
try: token=json.loads(result.stdout)['accessToken'].encode('utf-16-le')
except (KeyError,ValueError): raise SystemExit('Invalid token response; response withheld')
packed=struct.pack('<I',len(token))+token
try:
 with pyodbc.connect(f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{a.server},1433;Database=router;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;',attrs_before={1256:packed},autocommit=True) as db:
  # Do not silently adopt a non-router database containing unrelated tables.
  tables=set(row[0] for row in db.cursor().execute("SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0"))
  expected={'registry.Subscriptions','registry.Policies','delivery.Receipts','delivery.Outbox','delivery.RequestLog'}
  if tables and tables!=expected: raise RuntimeError('Unexpected database contents')
  # Existing schema compatibility must be reviewed separately before rerun.
  db.cursor().execute(a.schema.read_text())
  db.cursor().execute(a.grants.read_text())
 print('Router schema and scoped grants applied; no token output')
except Exception:
 raise SystemExit('SQL migration failed; inspect securely as operator (details withheld)')
finally:
 token=b'';packed=b'';result=None
