using System.Data;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Router.Core;
namespace Router.Storage;
public sealed class SqlRequestLog(string connection,TenantContext tenant,CaptureOptions options):IRequestLog {
    // Run from an approved scheduler with a tenant-bound retention identity.
    public async Task<int> PurgeExpiredAsync(CancellationToken ct) {
        tenant.Demand("requests:purge");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("DELETE TOP(1000) FROM delivery.RequestLog WHERE TenantId=@tenant AND Expires<=SYSUTCDATETIME()",db);
        cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);return await cmd.ExecuteNonQueryAsync(ct);
    }
    public async Task AppendAsync(CapturedRequest request,CancellationToken ct) {
        tenant.Demand("requests:append");_ = new RequestCapture(options);
        string document=JsonSerializer.Serialize(request);if(document.Length>20000)throw new ArgumentException("LOG_LIMIT");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var cmd=new SqlCommand("DELETE FROM delivery.RequestLog WHERE TenantId=@tenant AND Expires<=SYSUTCDATETIME(); INSERT delivery.RequestLog(TenantId,Id,Received,Expires,Document) VALUES(@tenant,@id,@received,@expires,@doc); DELETE FROM delivery.RequestLog WHERE TenantId=@tenant AND Sequence IN (SELECT Sequence FROM delivery.RequestLog WHERE TenantId=@tenant ORDER BY Sequence DESC OFFSET @max ROWS)",db,tx);
        cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);cmd.Parameters.AddWithValue("@id",request.Id);cmd.Parameters.AddWithValue("@received",request.Received);cmd.Parameters.AddWithValue("@expires",request.Received.AddDays(options.RetentionDays));cmd.Parameters.AddWithValue("@doc",document);cmd.Parameters.AddWithValue("@max",options.MaxRows);
        await cmd.ExecuteNonQueryAsync(ct);await tx.CommitAsync(ct);
    }
    public async Task<RequestLogPage> ListAsync(int limit,long? before,CancellationToken ct) {
        tenant.Demand("requests:read");if(limit is <1 or >100||before<=0)throw new ArgumentException("PAGE_INVALID");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("SELECT TOP(@count) Sequence,Document FROM delivery.RequestLog WHERE TenantId=@tenant AND Expires>SYSUTCDATETIME() AND (@before IS NULL OR Sequence<@before) ORDER BY Sequence DESC",db);
        cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);cmd.Parameters.AddWithValue("@count",limit+1);cmd.Parameters.Add("@before",SqlDbType.BigInt).Value=(object?)before??DBNull.Value;
        var items=new List<RequestLogRow>();await using var r=await cmd.ExecuteReaderAsync(ct);while(await r.ReadAsync(ct))items.Add(new(r.GetInt64(0),JsonSerializer.Deserialize<CapturedRequest>(r.GetString(1))!));
        bool more=items.Count>limit;if(more)items.RemoveAt(items.Count-1);return new(items,more?items[^1].Sequence:null);
    }
    public async Task<CapturedRequest?> FindAsync(string id,CancellationToken ct) {
        tenant.Demand("requests:read");if(id.Length!=32)return null;
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("SELECT Document FROM delivery.RequestLog WHERE TenantId=@tenant AND Id=@id AND Expires>SYSUTCDATETIME()",db);cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);cmd.Parameters.AddWithValue("@id",id);
        return await cmd.ExecuteScalarAsync(ct) is string json?JsonSerializer.Deserialize<CapturedRequest>(json):null;
    }
}
