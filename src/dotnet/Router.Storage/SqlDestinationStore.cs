using System.Data;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Router.Core;
namespace Router.Storage;
public sealed class SqlDestinationStore(string connection,TenantContext tenant):IDestinationStore {
 public async Task<DestinationPage> ListAsync(string tenantId,int limit,string? after,CancellationToken ct) {
  tenant.Match(tenantId);tenant.Demand("destinations:read");if(limit is <1 or >100)throw new ArgumentException("PAGE_INVALID");
  await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
  await using var cmd=new SqlCommand("SELECT TOP(@count) Id,Name,Tags,Enabled FROM registry.Destinations WHERE Owner=@owner AND (@after IS NULL OR Id>@after) ORDER BY Id",db);
  cmd.Parameters.AddWithValue("@count",limit+1);cmd.Parameters.AddWithValue("@owner",tenantId);cmd.Parameters.Add("@after",SqlDbType.VarChar,64).Value=(object?)after??DBNull.Value;
  var rows=new List<DestinationMetadata>();await using var reader=await cmd.ExecuteReaderAsync(ct);
  while(await reader.ReadAsync(ct))rows.Add(new(reader.GetString(0),reader.GetString(1),JsonSerializer.Deserialize<string[]>(reader.GetString(2))!,reader.GetBoolean(3)));
  bool more=rows.Count>limit;if(more)rows.RemoveAt(rows.Count-1);return new(rows,more?rows[^1].Id:null);
 }
 public async Task AddAsync(string tenantId,DestinationMetadata metadata,ProtectedDestination binding,CancellationToken ct) {
  tenant.Match(tenantId);tenant.Demand("destinations:write");if(metadata.Id!=binding.Id||metadata.Enabled)throw new ArgumentException("DESTINATION_INVALID");
  await using var db=new SqlConnection(connection);await db.OpenAsync(ct);await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
  await using var count=new SqlCommand("SELECT COUNT(*) FROM registry.Destinations WITH(UPDLOCK,HOLDLOCK) WHERE Owner=@owner",db,tx);count.Parameters.AddWithValue("@owner",tenantId);
  if(Convert.ToInt32(await count.ExecuteScalarAsync(ct))>=1024)throw new InvalidOperationException("DESTINATION_LIMIT");
  await using var cmd=new SqlCommand("INSERT registry.Destinations(Owner,Id,Name,Tags,Enabled) VALUES(@owner,@id,@name,@tags,0); INSERT delivery.DestinationConfig(Owner,Id,Endpoint,SigningKeyReference) VALUES(@owner,@id,@endpoint,@reference)",db,tx);
  cmd.Parameters.AddWithValue("@owner",tenantId);cmd.Parameters.AddWithValue("@id",metadata.Id);cmd.Parameters.AddWithValue("@name",metadata.Name);cmd.Parameters.AddWithValue("@tags",JsonSerializer.Serialize(metadata.Tags));cmd.Parameters.AddWithValue("@endpoint",binding.Endpoint.AbsoluteUri);cmd.Parameters.AddWithValue("@reference",binding.SigningKeyReference);
  await cmd.ExecuteNonQueryAsync(ct);await tx.CommitAsync(ct);
 }
 public Task UpdateAsync(string tenantId,string id,string name,string[] tags,CancellationToken ct)=>Mutate(tenantId,id,name,tags,null,ct);
 public Task SetEnabledAsync(string tenantId,string id,bool enabled,CancellationToken ct)=>Mutate(tenantId,id,null,null,enabled,ct);
 private async Task Mutate(string tenantId,string id,string? name,string[]? tags,bool? enabled,CancellationToken ct) {
  tenant.Match(tenantId);tenant.Demand("destinations:write");await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
  await using var cmd=new SqlCommand(enabled is null?"UPDATE registry.Destinations SET Name=@name,Tags=@tags WHERE Owner=@owner AND Id=@id":"UPDATE registry.Destinations SET Enabled=@enabled WHERE Owner=@owner AND Id=@id",db);
  cmd.Parameters.AddWithValue("@owner",tenantId);cmd.Parameters.AddWithValue("@id",id);
  if(enabled is bool value)cmd.Parameters.AddWithValue("@enabled",value);else {cmd.Parameters.AddWithValue("@name",name!);cmd.Parameters.AddWithValue("@tags",JsonSerializer.Serialize(tags));}
  if(await cmd.ExecuteNonQueryAsync(ct)!=1)throw new KeyNotFoundException("DESTINATION_NOT_FOUND");
 }
}
