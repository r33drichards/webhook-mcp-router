using Microsoft.Data.SqlClient;
using Router.Core;
using System.Text.Json;
namespace Router.Storage;
public sealed class SqlDestinationReader(string connection,TenantContext tenant):IDestinationReader {
    public async Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string tenantId,CancellationToken ct) {
        tenant.Match(tenantId);tenant.Demand("destinations:read");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var command=new SqlCommand("SELECT TOP(1025) Id,Name,Tags FROM registry.Destinations WHERE Owner=@owner AND Enabled=1 ORDER BY Id",db);
        command.Parameters.AddWithValue("@owner",tenantId);await using var reader=await command.ExecuteReaderAsync(ct);
        var result=new List<RegisteredDestination>();
        while(await reader.ReadAsync(ct))result.Add(new(tenantId,reader.GetString(0),reader.GetString(1),JsonSerializer.Deserialize<string[]>(reader.GetString(2))??throw new InvalidOperationException("DESTINATION_TAGS_INVALID")));
        if(result.Count>1024)throw new InvalidOperationException("DESTINATION_LIMIT");return result;
    }
}
public sealed class SqlDestinationResolver(string connection,TenantContext tenant):IDestinationResolver {
    public async Task<ProtectedDestination?> ResolveAsync(string tenantId,string id,CancellationToken ct) {
        tenant.Match(tenantId);tenant.Demand("destinations:deliver");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var command=new SqlCommand("SELECT c.Id,c.Endpoint,c.SigningKeyReference FROM delivery.DestinationConfig c JOIN registry.Destinations d ON c.Owner=d.Owner AND c.Id=d.Id WHERE c.Owner=@owner AND c.Id=@id AND d.Enabled=1",db);
        command.Parameters.AddWithValue("@owner",tenantId);command.Parameters.AddWithValue("@id",id);
        await using var reader=await command.ExecuteReaderAsync(ct);if(!await reader.ReadAsync(ct))return null;
        return new(reader.GetString(0),new Uri(reader.GetString(1),UriKind.Absolute),reader.GetString(2));
    }
}
