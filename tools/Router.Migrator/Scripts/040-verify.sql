DECLARE @expected table(Name nvarchar(256));
INSERT @expected VALUES('registry.Subscriptions'),('registry.Policies'),('registry.Destinations'),('delivery.Receipts'),('delivery.Outbox'),('delivery.RequestLog'),('delivery.DestinationConfig'),('delivery.WebhookOutbox');
IF EXISTS(SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0 EXCEPT SELECT Name FROM @expected)
OR EXISTS(SELECT Name FROM @expected EXCEPT SELECT SCHEMA_NAME(schema_id)+'.'+name FROM sys.tables WHERE is_ms_shipped=0)
THROW 51000,'MIGRATION_TABLE_SET_MISMATCH',1;
