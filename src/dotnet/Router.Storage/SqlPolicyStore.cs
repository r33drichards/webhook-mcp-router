using System.Data;
using Microsoft.Data.SqlClient;
using Router.Core;
namespace Router.Storage;

// Bound to the authenticated tenant. Serializable range locks protect initial
// creation and CAS across all policies in that tenant, not only one requested ID.
public sealed class SqlPolicyStore(string connection,TenantContext tenant):IPolicyStore {
    public async Task<ManagedPolicy?> GetAsync(CancellationToken ct){
        tenant.Demand("policies:read");
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var cmd=new SqlCommand("SELECT TOP(2) Id,Source,Revision FROM registry.Policies WHERE Owner=@owner ORDER BY Id",db);
        cmd.Parameters.AddWithValue("@owner",tenant.TenantId);
        await using var r=await cmd.ExecuteReaderAsync(ct);
        if(!await r.ReadAsync(ct))return null;
        var value=new ManagedPolicy(r.GetString(0),r.GetString(1),Convert.ToHexStringLower((byte[])r[2]));
        if(await r.ReadAsync(ct))throw new InvalidOperationException("POLICY_CONFIGURATION");return value;
    }
    public async Task<ManagedPolicy> ApplyAsync(string id,string source,string? expectedRevision,CancellationToken ct){
        tenant.Demand("policies:write");PolicyManagement.Identifier(id);PolicyManagement.Source(source);PolicyManagement.Revision(expectedRevision);
        await using var db=new SqlConnection(connection);await db.OpenAsync(ct);
        await using var tx=(SqlTransaction)await db.BeginTransactionAsync(IsolationLevel.Serializable,ct);
        await using var read=new SqlCommand("SELECT TOP(2) Id,Revision FROM registry.Policies WITH(UPDLOCK,HOLDLOCK) WHERE Owner=@owner ORDER BY Id",db,tx);
        read.Parameters.AddWithValue("@owner",tenant.TenantId);string? currentId=null,revision=null;
        await using(var r=await read.ExecuteReaderAsync(ct)){
            if(await r.ReadAsync(ct)){currentId=r.GetString(0);revision=Convert.ToHexStringLower((byte[])r[1]);if(await r.ReadAsync(ct))throw new InvalidOperationException("POLICY_CONFIGURATION");}
        }
        if(currentId is null?expectedRevision is not null:currentId!=id||revision!=expectedRevision)throw new InvalidOperationException("POLICY_VERSION_CONFLICT");
        string sql=currentId is null?"INSERT registry.Policies(Owner,Id,Source) OUTPUT inserted.Revision VALUES(@owner,@id,@source)":"UPDATE registry.Policies SET Source=@source OUTPUT inserted.Revision WHERE Owner=@owner AND Id=@id AND Revision=@revision";
        await using var cmd=new SqlCommand(sql,db,tx);cmd.Parameters.AddWithValue("@owner",tenant.TenantId);cmd.Parameters.AddWithValue("@id",id);cmd.Parameters.AddWithValue("@source",source);
        if(revision is not null)cmd.Parameters.Add("@revision",SqlDbType.Binary,8).Value=Convert.FromHexString(revision);
        var result=await cmd.ExecuteScalarAsync(ct) as byte[]??throw new InvalidOperationException("POLICY_VERSION_CONFLICT");
        await tx.CommitAsync(ct);return new(id,source,Convert.ToHexStringLower(result));
    }
}
