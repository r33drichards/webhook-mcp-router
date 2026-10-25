using System.Data;
using System.Reflection;
using Microsoft.Data.SqlClient;
using Router.Core;

namespace Router.Storage;

public static class SqlMigration {
    public static async Task ApplyAsync(string connection, CancellationToken ct = default) {
        await using var db = new SqlConnection(connection); await db.OpenAsync(ct);
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Router.Storage.schema.sql")!;
        string text = await new StreamReader(stream).ReadToEndAsync(ct);
        await using var command = new SqlCommand(text, db); await command.ExecuteNonQueryAsync(ct);
    }
}

// Reader and writer constructed with separate least-privilege connections.
public sealed class SqlRegistrationReader(string connection,TenantContext tenant) : IRegistrationReader {
    public async Task<RegistrationSnapshot> SnapshotAsync(string owner, CancellationToken ct) {
        tenant.Match(owner);
        await using var db = new SqlConnection(connection); await db.OpenAsync(ct);
        await using var tx = (SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var cmd = new SqlCommand("SELECT Id,Source FROM registry.Policies WHERE Owner=@owner ORDER BY Id; SELECT Id,Owner,Name,Arguments,Callback,KeyFingerprint,Expires FROM registry.Subscriptions WHERE Owner=@owner AND Expires>SYSUTCDATETIME() ORDER BY Id",db,tx);
        cmd.Parameters.AddWithValue("@owner",owner);
        var policies = new List<StoredPolicy>(); var subscriptions = new List<Subscription>();
        await using (var reader=await cmd.ExecuteReaderAsync(ct)) {
            while(await reader.ReadAsync(ct)) policies.Add(new(reader.GetString(0),reader.GetString(1)));
            await reader.NextResultAsync(ct);
            while(await reader.ReadAsync(ct)) subscriptions.Add(new(reader.GetString(0),reader.GetString(1),reader.GetString(2),reader.GetString(3),reader.GetString(4),reader.GetString(5),reader.GetFieldValue<DateTimeOffset>(6)));
        }
        await tx.CommitAsync(ct); return new(policies,subscriptions);
    }
}

public sealed class SqlRegistrationWriter(string connection,TenantContext tenant) : IRegistrationWriter {
    public async Task SaveSubscriptionAsync(Subscription value, CancellationToken ct) {
        tenant.Match(value.Owner);tenant.Demand("subscriptions:write");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var cmd=new SqlCommand("UPDATE registry.Subscriptions WITH(UPDLOCK,HOLDLOCK) SET Name=@name,Arguments=@args,Callback=@url,KeyFingerprint=@key,Expires=@expires WHERE Id=@id AND Owner=@owner; IF @@ROWCOUNT=0 INSERT registry.Subscriptions(Id,Owner,Name,Arguments,Callback,KeyFingerprint,Expires) VALUES(@id,@owner,@name,@args,@url,@key,@expires);",db,tx);
        cmd.Parameters.AddWithValue("@id",value.Id);cmd.Parameters.AddWithValue("@owner",value.Owner);cmd.Parameters.AddWithValue("@name",value.Name);cmd.Parameters.AddWithValue("@args",value.Arguments);cmd.Parameters.AddWithValue("@url",value.Callback);cmd.Parameters.AddWithValue("@key",value.KeyFingerprint);cmd.Parameters.AddWithValue("@expires",value.Expires);
        await cmd.ExecuteNonQueryAsync(ct);await tx.CommitAsync(ct);
    }
    public async Task DeleteSubscriptionAsync(string owner,string id,CancellationToken ct) {
        tenant.Match(owner);tenant.Demand("subscriptions:write");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("DELETE registry.Subscriptions WHERE Owner=@owner AND Id=@id",db);
        cmd.Parameters.AddWithValue("@owner",owner);cmd.Parameters.AddWithValue("@id",id);await cmd.ExecuteNonQueryAsync(ct);
    }
    public async Task SavePolicyAsync(string owner,StoredPolicy policy,CancellationToken ct) {
        tenant.Match(owner);tenant.Demand("policies:write");
        if(policy.Source.Length>32768 || policy.Id.Length is 0 or >64)throw new ArgumentException("POLICY_LIMIT");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var cmd=new SqlCommand("UPDATE registry.Policies WITH(UPDLOCK,HOLDLOCK) SET Source=@source WHERE Owner=@owner AND Id=@id; IF @@ROWCOUNT=0 INSERT registry.Policies(Owner,Id,Source) VALUES(@owner,@id,@source)",db,tx);
        cmd.Parameters.AddWithValue("@owner",owner);cmd.Parameters.AddWithValue("@id",policy.Id);cmd.Parameters.AddWithValue("@source",policy.Source);await cmd.ExecuteNonQueryAsync(ct);await tx.CommitAsync(ct);
    }
}

// Separate delivery authority: never writes registry tables.
public sealed class SqlOutbox(string connection,TenantContext tenant) : IOutbox {
    public async Task<bool> AcceptAsync(string source,string deliveryId,string bodyHash,IReadOnlyList<PendingDelivery> deliveries,CancellationToken ct) {
        if(source.Length is 0 or >64 || deliveryId.Length is 0 or >128 || bodyHash.Length!=64 || deliveries.Count>256 || deliveries.Any(d=>d.Body.Length>32768))throw new ArgumentException("DELIVERY_LIMIT");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var check=new SqlCommand("SELECT BodyHash FROM delivery.Receipts WITH(UPDLOCK,HOLDLOCK) WHERE TenantId=@tenant AND Source=@source AND DeliveryId=@id",db,tx);
        check.Parameters.AddWithValue("@tenant",tenant.TenantId);check.Parameters.AddWithValue("@source",source);check.Parameters.AddWithValue("@id",deliveryId);
        var previous=await check.ExecuteScalarAsync(ct);
        if(previous is string hash) {
            if(hash!=bodyHash)throw new InvalidOperationException("DELIVERY_ID_CONFLICT");
            await tx.CommitAsync(ct);return false;
        }
        await using var receipt=new SqlCommand("INSERT delivery.Receipts(TenantId,Source,DeliveryId,BodyHash) VALUES(@tenant,@source,@id,@hash)",db,tx);
        receipt.Parameters.AddWithValue("@tenant",tenant.TenantId);receipt.Parameters.AddWithValue("@source",source);receipt.Parameters.AddWithValue("@id",deliveryId);receipt.Parameters.AddWithValue("@hash",bodyHash);await receipt.ExecuteNonQueryAsync(ct);
        foreach(var item in deliveries) {
            await using var insert=new SqlCommand("INSERT delivery.Outbox(TenantId,Id,SubscriptionId,Body) VALUES(@tenant,@id,@sub,@body)",db,tx);
            insert.Parameters.AddWithValue("@tenant",tenant.TenantId);insert.Parameters.AddWithValue("@id",item.Id);insert.Parameters.AddWithValue("@sub",item.SubscriptionId);insert.Parameters.AddWithValue("@body",item.Body);await insert.ExecuteNonQueryAsync(ct);
        }
        await tx.CommitAsync(ct);return true;
    }
    public async Task<ClaimedDelivery?> ClaimAsync(TimeSpan leaseTime,CancellationToken ct) {
        int seconds=(int)leaseTime.TotalSeconds;if(seconds is <1 or >300)throw new ArgumentException("LEASE_LIMIT");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("UPDATE TOP(1) delivery.Outbox WITH(UPDLOCK,READPAST,READCOMMITTEDLOCK) SET Lease=@lease,LeaseUntil=DATEADD(second,@seconds,SYSUTCDATETIME()),Attempts=Attempts+1 OUTPUT inserted.Id,inserted.SubscriptionId,inserted.Body,inserted.Lease,inserted.Attempts WHERE TenantId=@tenant AND Status='pending' AND Available<=SYSUTCDATETIME() AND (LeaseUntil IS NULL OR LeaseUntil<=SYSUTCDATETIME())",db);
        cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);cmd.Parameters.AddWithValue("@lease",Guid.NewGuid());cmd.Parameters.AddWithValue("@seconds",seconds);
        await using var r=await cmd.ExecuteReaderAsync(ct);return await r.ReadAsync(ct)?new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetGuid(3),r.GetInt32(4)):null;
    }
    public Task<bool> CompleteAsync(string id,Guid lease,CancellationToken ct)=>UpdateAsync(id,lease,0,0,true,ct);
    public Task<bool> RetryAsync(string id,Guid lease,TimeSpan delay,int maxAttempts,CancellationToken ct)=>UpdateAsync(id,lease,(int)delay.TotalSeconds,maxAttempts,false,ct);
    private async Task<bool> UpdateAsync(string id,Guid lease,int delay,int max,bool complete,CancellationToken ct) {
        if(delay is <0 or >86400 || (!complete && max is <1 or >20))throw new ArgumentException("RETRY_LIMIT");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        string sql=complete?"UPDATE delivery.Outbox SET Status='done',Lease=NULL,LeaseUntil=NULL WHERE TenantId=@tenant AND Id=@id AND Lease=@lease AND LeaseUntil>SYSUTCDATETIME() AND Status='pending'":"UPDATE delivery.Outbox SET Status=CASE WHEN Attempts>=@max THEN 'dead' ELSE 'pending' END,Available=DATEADD(second,@delay,SYSUTCDATETIME()),Lease=NULL,LeaseUntil=NULL WHERE TenantId=@tenant AND Id=@id AND Lease=@lease AND LeaseUntil>SYSUTCDATETIME() AND Status='pending'";
        await using var cmd=new SqlCommand(sql,db);cmd.Parameters.AddWithValue("@tenant",tenant.TenantId);cmd.Parameters.AddWithValue("@id",id);cmd.Parameters.AddWithValue("@lease",lease);cmd.Parameters.AddWithValue("@max",max);cmd.Parameters.AddWithValue("@delay",delay);return await cmd.ExecuteNonQueryAsync(ct)==1;
    }
}
