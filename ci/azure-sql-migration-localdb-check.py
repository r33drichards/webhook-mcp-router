"""Real Windows LocalDB qualification of the fresh migration transaction.
No Azure login or cloud credentials. Does not prove Entra managed-identity grants.
"""
import importlib.util, pathlib, uuid
import pyodbc
root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('migration',root/'deploy/azure/runtime/migration-plan.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
drivers=pyodbc.drivers()
driver=next((x for x in ['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'] if x in drivers),None)
if not driver:raise SystemExit('SQL_SERVER_ODBC_DRIVER_MISSING')
# Integrated Windows LocalDB uses local IPC and does not support ODBC TLS.
# No remote host parameter is accepted; production migration retains verified TLS.
base=f'Driver={{{driver}}};Server=(localdb)\\MSSQLLocalDB;Trusted_Connection=yes;Encrypt=no;'
name='router_migration_'+uuid.uuid4().hex
master=pyodbc.connect(base+'Database=master;',autocommit=True)
try:
    master.execute(f'CREATE DATABASE [{name}]')
    with pyodbc.connect(base+f'Database={name};',autocommit=False) as db:
        try:m.apply_fresh(db,"THROW 51000,'synthetic grant failure',1;")
        except pyodbc.Error:pass
        else:raise AssertionError('Expected SQL grant failure')
        assert not list(db.execute('SELECT name FROM sys.tables WHERE is_ms_shipped=0'))
        db.rollback()
        print('PASS actual SQL rolls back both schemas on grant failure')
        m.apply_fresh(db,"CREATE USER [router_fixture_reader] WITHOUT LOGIN; GRANT SELECT ON OBJECT::registry.Destinations TO [router_fixture_reader];")
        assert {r[0] for r in db.execute("SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0")}==m.TABLES
        db.rollback()
        print('PASS actual SQL commits exact eight-table schema and synthetic object grant')
        try:m.apply_fresh(db,'SELECT 1;')
        except ValueError as e:assert str(e)=='NONEMPTY_DATABASE_REQUIRES_REVIEWED_MIGRATION'
        else:raise AssertionError('Unexpected repeat migration')
        assert len(list(db.execute('SELECT name FROM sys.tables WHERE is_ms_shipped=0')))==8
        db.rollback()
        print('PASS repeat migration fails without changing existing schema')
finally:
    master.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
    master.execute(f'DROP DATABASE [{name}]')
    master.close()
print('LIMIT: Azure Entra SID principals and managed-identity permissions require Azure qualification.')
