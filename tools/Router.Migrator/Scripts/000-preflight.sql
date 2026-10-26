SET XACT_ABORT ON;
IF DB_NAME()<>N'router' THROW 51000,'DATABASE_DENIED',1;
DECLARE @result int;
EXEC @result=sys.sp_getapplock @Resource=N'webhook-router-fresh-migration',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=0;
IF @result<0 THROW 51000,'MIGRATION_LOCK_UNAVAILABLE',1;
IF SCHEMA_ID('registry') IS NULL OR SCHEMA_ID('delivery') IS NULL THROW 51000,'BOOTSTRAP_SCHEMAS_REQUIRED',1;
IF OBJECT_ID('registry.SchemaVersions','U') IS NULL
BEGIN
 IF EXISTS(SELECT 1 FROM sys.tables WHERE is_ms_shipped=0) THROW 51000,'UNJOURNALED_DATABASE_REQUIRES_REVIEW',1;
 CREATE TABLE registry.SchemaVersions(
  ScriptName nvarchar(255) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY,
  ContentHash char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
  AppliedUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
 );
END;
IF NOT EXISTS(SELECT 1 FROM registry.SchemaVersions)
 AND EXISTS(SELECT 1 FROM sys.tables WHERE is_ms_shipped=0 AND object_id<>OBJECT_ID('registry.SchemaVersions'))
 THROW 51000,'UNJOURNALED_DATABASE_REQUIRES_REVIEW',1;
IF EXISTS(SELECT 1 FROM registry.SchemaVersions)
 AND (OBJECT_ID('registry.Subscriptions','U') IS NULL OR OBJECT_ID('registry.Policies','U') IS NULL
 OR OBJECT_ID('registry.Destinations','U') IS NULL OR OBJECT_ID('delivery.Receipts','U') IS NULL
 OR OBJECT_ID('delivery.Outbox','U') IS NULL OR OBJECT_ID('delivery.RequestLog','U') IS NULL
 OR OBJECT_ID('delivery.DestinationConfig','U') IS NULL OR OBJECT_ID('delivery.WebhookOutbox','U') IS NULL)
 THROW 51000,'BASELINE_OBJECT_MISSING',1;
