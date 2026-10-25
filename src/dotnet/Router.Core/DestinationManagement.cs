namespace Router.Core;

public sealed record DestinationMetadata(string Id,string Name,string[] Tags,bool Enabled);
public sealed record DestinationPage(IReadOnlyList<DestinationMetadata> Items,string? NextAfter);
public sealed record DestinationBinding(string Id,string Endpoint,string SigningKeyReference);
public interface IDestinationStore {
 Task<DestinationPage> ListAsync(string tenantId,int limit,string? after,CancellationToken ct);
 Task AddAsync(string tenantId,DestinationMetadata metadata,ProtectedDestination binding,CancellationToken ct);
 Task UpdateAsync(string tenantId,string id,string name,string[] tags,CancellationToken ct);
 Task SetEnabledAsync(string tenantId,string id,bool enabled,CancellationToken ct);
}
public sealed class DestinationManagement {
 private readonly TenantContext tenant;private readonly IDestinationStore store;private readonly Dictionary<string,DestinationBinding> bindings;
 public DestinationManagement(TenantContext tenant,IDestinationStore store,IEnumerable<DestinationBinding> bindings) {
  this.tenant=tenant;this.store=store;this.bindings=bindings.ToDictionary(b=>b.Id,StringComparer.Ordinal);
  if(this.bindings.Count>64)throw new ArgumentException("BINDING_LIMIT");
  foreach(var b in this.bindings.Values){Id(b.Id);Id(b.SigningKeyReference);SafeWebhookTransport.ValidateEndpoint(new Uri(b.Endpoint,UriKind.Absolute));}
 }
 public static void Id(string id){if(string.IsNullOrEmpty(id)||id.Length>64||id.Any(c=>!char.IsAsciiLetterOrDigit(c)&&c is not ('_' or '-')))throw new ArgumentException("IDENTIFIER_INVALID");}
 private static void Metadata(string name,string[] tags){if(string.IsNullOrWhiteSpace(name)||name.Length>128||name.Any(char.IsControl)||tags.Length>32||tags.Distinct(StringComparer.Ordinal).Count()!=tags.Length)throw new ArgumentException("METADATA_INVALID");foreach(var tag in tags)Id(tag);}
 public IReadOnlyList<string> Bindings(){tenant.Demand("destinations:write");return bindings.Keys.Order(StringComparer.Ordinal).ToArray();}
 public Task<DestinationPage> ListAsync(int limit=25,string? after=null,CancellationToken ct=default){tenant.Demand("destinations:read");if(limit is <1 or >100)throw new ArgumentException("PAGE_INVALID");if(after is not null)Id(after);return store.ListAsync(tenant.TenantId,limit,after,ct);}
 public async Task<DestinationMetadata> RegisterAsync(string bindingId,string name,string[] tags,CancellationToken ct=default) {
  tenant.Demand("destinations:write");Metadata(name,tags);if(!bindings.TryGetValue(bindingId,out var binding))throw new UnauthorizedAccessException("BINDING_DENIED");
  var result=new DestinationMetadata("dst_"+Guid.NewGuid().ToString("N"),name,tags.ToArray(),false);
  await store.AddAsync(tenant.TenantId,result,new(result.Id,new Uri(binding.Endpoint),binding.SigningKeyReference),ct);return result;
 }
 public Task UpdateAsync(string id,string name,string[] tags,CancellationToken ct=default){tenant.Demand("destinations:write");Id(id);Metadata(name,tags);return store.UpdateAsync(tenant.TenantId,id,name,tags.ToArray(),ct);}
 public Task SetEnabledAsync(string id,bool enabled,CancellationToken ct=default){tenant.Demand("destinations:write");Id(id);return store.SetEnabledAsync(tenant.TenantId,id,enabled,ct);}
}
