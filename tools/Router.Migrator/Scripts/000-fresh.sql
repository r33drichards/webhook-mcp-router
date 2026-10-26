SET XACT_ABORT ON;
DECLARE @result int;
EXEC @result=sys.sp_getapplock @Resource=N'webhook-router-fresh-migration',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=0;
IF @result < 0 THROW 51000,'MIGRATION_LOCK_UNAVAILABLE',1;
IF DB_NAME()<>N'router' THROW 51000,'DATABASE_DENIED',1;
IF EXISTS(SELECT 1 FROM sys.tables WHERE is_ms_shipped=0) THROW 51000,'NONEMPTY_DATABASE_REQUIRES_REVIEW',1;
IF SCHEMA_ID('registry') IS NULL OR SCHEMA_ID('delivery') IS NULL THROW 51000,'BOOTSTRAP_SCHEMAS_REQUIRED',1;
