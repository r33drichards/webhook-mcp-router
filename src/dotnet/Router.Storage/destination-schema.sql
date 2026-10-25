-- Explicit optional migration; not run by existing ingress or phase2 deployment.
IF SCHEMA_ID('registry') IS NULL EXEC('CREATE SCHEMA registry');
IF OBJECT_ID('registry.Destinations') IS NULL
CREATE TABLE registry.Destinations (
 Owner varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL, Id varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
 Name nvarchar(128) NOT NULL, Tags nvarchar(4000) NOT NULL,
 Enabled bit NOT NULL DEFAULT 0, Revision rowversion NOT NULL,
 PRIMARY KEY(Owner,Id), CONSTRAINT DestinationTags_JSON CHECK(ISJSON(Tags)=1)
);
-- URL/auth configuration is intentionally not part of this metadata table/API.
-- Protected configuration storage and dispatcher resolution remain separate work.
IF SCHEMA_ID('delivery') IS NULL EXEC('CREATE SCHEMA delivery');
IF OBJECT_ID('delivery.DestinationConfig') IS NULL
CREATE TABLE delivery.DestinationConfig (
 Owner varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL, Id varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
 Endpoint nvarchar(2048) NOT NULL, SigningKeyReference nvarchar(256) NOT NULL,
 PRIMARY KEY(Owner,Id), FOREIGN KEY(Owner,Id) REFERENCES registry.Destinations(Owner,Id)
);
-- Endpoint/reference bindings are immutable under application UPDATE authority.
-- Changing a URL requires a new destination ID; disable old metadata first.
EXEC('CREATE OR ALTER TRIGGER delivery.DestinationConfigImmutable ON delivery.DestinationConfig INSTEAD OF UPDATE AS BEGIN THROW 51000, ''Destination binding is immutable; register a new ID'', 1; END');
IF OBJECT_ID('delivery.WebhookOutbox') IS NULL
CREATE TABLE delivery.WebhookOutbox (
 TenantId varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL, Id varchar(68) COLLATE Latin1_General_100_BIN2 NOT NULL, DestinationId varchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
 Body nvarchar(max) NOT NULL, Status varchar(8) NOT NULL DEFAULT 'pending',
 Available datetime2 NOT NULL DEFAULT SYSUTCDATETIME(), Lease uniqueidentifier NULL,
 LeaseUntil datetime2 NULL, Attempts int NOT NULL DEFAULT 0,
 PRIMARY KEY(TenantId,Id), CONSTRAINT WebhookOutbox_Status CHECK(Status IN ('pending','done','dead'))
);
-- App roles: metadata reader SELECT registry.Destinations only;
-- control metadata CRUD as reviewed, protected binding INSERT only (no DELETE/UPDATE);
-- delivery SELECT protected binding plus WebhookOutbox DML/receipt authority.
-- Do not grant these automatically; supervisor reviews the migration/grants.
