using Microsoft.Data.SqlClient;
using System.Security.Cryptography;
using System.Text;

namespace Router.SqlBootstrap;
public static class Bootstrap {
 public const string Tenant="0e4545fd-804f-4acb-ad41-f955e53645c1";
 public const string Administrator="9e61efd9-e30d-4bda-93bb-c952234dfe67";
 public const string Server="sql-webhook-mcp-router-v2-f7076f8e38.database.windows.net";
 public static readonly Guid Reader=new("04ae4ee5-f138-4fd0-8b88-c5ae854eced5");
 public static readonly Guid Control=new("17f79290-9166-4206-8792-bda6a541b8b2");
 public static readonly Guid Delivery=new("c6255f93-5ebb-4825-b7a1-42325124d72b");
 public static string Sid(Guid id)=>"0x"+Convert.ToHexString(id.ToByteArray()).ToLowerInvariant();
 public static string Hash(string sql)=>Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sql)));
 public static string Build(Guid migrator) {
  if(migrator==Guid.Empty || new[]{Reader,Control,Delivery}.Contains(migrator))throw new ArgumentException("DISTINCT_MIGRATOR_REQUIRED");
  var s=new StringBuilder("""
SET XACT_ABORT ON;
IF DB_NAME()<>N'router' THROW 51000,'DATABASE_DENIED',1;
DECLARE @lock int;
EXEC @lock=sys.sp_getapplock @Resource=N'webhook-router-fresh-migration',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=0;
IF @lock<0 THROW 51000,'BOOTSTRAP_LOCK_UNAVAILABLE',1;
IF EXISTS(SELECT 1 FROM sys.tables WHERE is_ms_shipped=0) THROW 51000,'NONEMPTY_DATABASE_REQUIRES_REVIEW',1;
IF EXISTS(SELECT 1 FROM sys.schemas WHERE name IN ('registry','delivery') AND principal_id<>USER_ID('dbo')) THROW 51000,'SCHEMA_OWNER_MISMATCH',1;
IF SCHEMA_ID('registry') IS NULL EXEC('CREATE SCHEMA registry AUTHORIZATION dbo');
IF SCHEMA_ID('delivery') IS NULL EXEC('CREATE SCHEMA delivery AUTHORIZATION dbo');

""");
  foreach(var user in new[]{("router_reader",Reader),("router_control",Control),("router_delivery",Delivery),("router_migrator",migrator)}) {
   s.AppendLine($"IF EXISTS(SELECT 1 FROM sys.database_principals WHERE name=N'{user.Item1}' AND (sid<>{Sid(user.Item2)} OR type<>'E')) THROW 51000,'PRINCIPAL_MISMATCH',1;");
   s.AppendLine($"IF NOT EXISTS(SELECT 1 FROM sys.database_principals WHERE name=N'{user.Item1}') CREATE USER [{user.Item1}] WITH SID={Sid(user.Item2)}, TYPE=E;");
  }
  s.AppendLine("""
DECLARE @allowed table(principal_id int,class int,major_id int,minor_id int,permission_name nvarchar(128),state char(1));
INSERT @allowed SELECT principal_id,0,0,0,'CONNECT','G' FROM sys.database_principals WHERE name IN ('router_reader','router_control','router_delivery','router_migrator');
INSERT @allowed VALUES(USER_ID('router_migrator'),0,0,0,'CREATE TABLE','G'),(USER_ID('router_migrator'),0,0,0,'VIEW DEFINITION','G'),(USER_ID('router_migrator'),3,SCHEMA_ID('registry'),0,'CONTROL','G'),(USER_ID('router_migrator'),3,SCHEMA_ID('delivery'),0,'CONTROL','G');
IF EXISTS(SELECT 1 FROM sys.database_role_members WHERE member_principal_id IN (SELECT principal_id FROM @allowed)) THROW 51000,'EXISTING_ROLE_MEMBERSHIP_DENIED',1;
IF EXISTS(SELECT grantee_principal_id,class,major_id,minor_id,permission_name COLLATE DATABASE_DEFAULT,state COLLATE DATABASE_DEFAULT FROM sys.database_permissions WHERE grantee_principal_id IN (SELECT principal_id FROM @allowed) EXCEPT SELECT * FROM @allowed) THROW 51000,'EXISTING_PERMISSION_DENIED',1;
GRANT CONNECT TO [router_reader];
GRANT CONNECT TO [router_control];
GRANT CONNECT TO [router_delivery];
GRANT CONNECT TO [router_migrator];
GRANT CREATE TABLE,VIEW DEFINITION TO [router_migrator];
GRANT CONTROL ON SCHEMA::registry TO [router_migrator];
GRANT CONTROL ON SCHEMA::delivery TO [router_migrator];
IF EXISTS(SELECT * FROM @allowed EXCEPT SELECT grantee_principal_id,class,major_id,minor_id,permission_name COLLATE DATABASE_DEFAULT,state COLLATE DATABASE_DEFAULT FROM sys.database_permissions) THROW 51000,'GRANT_READBACK_FAILED',1;
IF EXISTS(SELECT grantee_principal_id,class,major_id,minor_id,permission_name COLLATE DATABASE_DEFAULT,state COLLATE DATABASE_DEFAULT FROM sys.database_permissions WHERE grantee_principal_id IN (SELECT principal_id FROM @allowed) EXCEPT SELECT * FROM @allowed) THROW 51000,'UNEXPECTED_GRANT',1;
""");
  return s.ToString();
 }
 public static async Task Execute(SqlConnection connection,string reviewedSql,CancellationToken cancellation=default) {
  await connection.OpenAsync(cancellation);
  using var transaction=connection.BeginTransaction();
  try {
   using var command=new SqlCommand(reviewedSql,connection,transaction){CommandTimeout=60};
   await command.ExecuteNonQueryAsync(cancellation);transaction.Commit();
  } catch {try{transaction.Rollback();}catch{/* Caller reports failure/uncertainty; never retry automatically. */}throw;}
 }
}
