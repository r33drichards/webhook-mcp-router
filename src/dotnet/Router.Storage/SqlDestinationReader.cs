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
