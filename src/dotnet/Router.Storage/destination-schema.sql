-- Explicit optional migration; not run by existing ingress or phase2 deployment.
IF SCHEMA_ID('registry') IS NULL EXEC('CREATE SCHEMA registry');
IF OBJECT_ID('registry.Destinations') IS NULL
CREATE TABLE registry.Destinations (
 Owner varchar(64) NOT NULL, Id varchar(64) NOT NULL,
 Name nvarchar(128) NOT NULL, Tags nvarchar(4096) NOT NULL,
 Enabled bit NOT NULL DEFAULT 0, Revision rowversion NOT NULL,
 PRIMARY KEY(Owner,Id), CONSTRAINT DestinationTags_JSON CHECK(ISJSON(Tags)=1)
);
-- URL/auth configuration is intentionally not part of this metadata table/API.
-- Protected configuration storage and dispatcher resolution remain separate work.
