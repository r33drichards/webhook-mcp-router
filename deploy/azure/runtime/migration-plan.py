"""Offline fresh-database migration plan. No Azure login or SQL writes here."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ('src/dotnet/Router.Storage/schema.sql', 'src/dotnet/Router.Storage/destination-schema.sql')
TABLES = frozenset({'registry.Subscriptions', 'registry.Policies', 'delivery.Receipts', 'delivery.Outbox', 'delivery.RequestLog', 'registry.Destinations', 'delivery.DestinationConfig', 'delivery.WebhookOutbox'})

def require_fresh(tables):
    if set(tables):
        raise ValueError('NONEMPTY_DATABASE_REQUIRES_REVIEWED_MIGRATION')

def manifest():
    return [{'path': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in SCHEMAS]

def apply_fresh(db, grants):
    """Connection must have autocommit=False; all schema/grants share its transaction."""
    if db.autocommit:
        raise ValueError('TRANSACTION_REQUIRED')
    try:
        cursor = db.cursor()
        require_fresh(row[0] for row in cursor.execute("SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0"))
        for name in SCHEMAS:
            cursor.execute((ROOT/name).read_text())
        observed = {row[0] for row in cursor.execute("SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0")}
        if observed != TABLES:
            raise ValueError('MIGRATION_TABLE_SET_MISMATCH')
        cursor.execute(grants)
        db.commit()
    except Exception:
        db.rollback()
        raise

if __name__ == '__main__':
    import json
    print(json.dumps({'mode':'fresh-only', 'schemas':manifest(), 'tables':sorted(TABLES)}, indent=2))
