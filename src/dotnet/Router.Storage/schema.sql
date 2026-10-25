-- Fresh synthetic database schema only; no automatic migration of an existing schema.
-- Explicit migration, never executed automatically by a request.
IF SCHEMA_ID('registry') IS NULL EXEC('CREATE SCHEMA registry');
IF SCHEMA_ID('delivery') IS NULL EXEC('CREATE SCHEMA delivery');
IF OBJECT_ID('registry.Subscriptions') IS NULL
CREATE TABLE registry.Subscriptions (
 Id varchar(68) NOT NULL, Owner varchar(64) NOT NULL,
 Name nvarchar(128) NOT NULL, Arguments nvarchar(4000) NOT NULL,
 Callback nvarchar(2048) NOT NULL, KeyFingerprint varchar(64) NOT NULL,
 Expires datetimeoffset NOT NULL, Revision rowversion NOT NULL, PRIMARY KEY(Owner,Id)
);
IF OBJECT_ID('registry.Policies') IS NULL
CREATE TABLE registry.Policies (
 Owner varchar(64) NOT NULL, Id varchar(64) NOT NULL, Source nvarchar(max) NOT NULL,
 Revision rowversion NOT NULL, PRIMARY KEY(Owner,Id)
);
IF OBJECT_ID('delivery.Receipts') IS NULL
CREATE TABLE delivery.Receipts (
 TenantId varchar(64) NOT NULL, Source varchar(64) NOT NULL, DeliveryId varchar(128) NOT NULL,
 BodyHash char(64) NOT NULL, Accepted datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 PRIMARY KEY(TenantId,Source,DeliveryId)
);
IF OBJECT_ID('delivery.Outbox') IS NULL
CREATE TABLE delivery.Outbox (
 TenantId varchar(64) NOT NULL, Id varchar(68) NOT NULL, SubscriptionId varchar(68) NOT NULL,
 Body nvarchar(max) NOT NULL, Status varchar(8) NOT NULL DEFAULT 'pending',
 Available datetime2 NOT NULL DEFAULT SYSUTCDATETIME(), Lease uniqueidentifier NULL,
 LeaseUntil datetime2 NULL, Attempts int NOT NULL DEFAULT 0,
 PRIMARY KEY(TenantId,Id),
 CONSTRAINT Outbox_Status CHECK(Status IN ('pending','done','dead'))
);
IF OBJECT_ID('delivery.RequestLog') IS NULL
CREATE TABLE delivery.RequestLog (
 Sequence bigint IDENTITY NOT NULL PRIMARY KEY, TenantId varchar(64) NOT NULL,
 Id char(32) NOT NULL, Received datetimeoffset NOT NULL, Expires datetimeoffset NOT NULL,
 Document nvarchar(max) NOT NULL, UNIQUE(TenantId,Id)
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='RequestLog_TenantSequence' AND object_id=OBJECT_ID('delivery.RequestLog'))
CREATE INDEX RequestLog_TenantSequence ON delivery.RequestLog(TenantId,Sequence DESC) INCLUDE(Expires);
