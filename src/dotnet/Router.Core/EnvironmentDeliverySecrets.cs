using System.Text.Json;
namespace Router.Core;
// Only reads protected operator settings. No fallback to arbitrary environment keys,
// developer credentials, Key Vault URLs, or tenant IDs supplied by an MCP caller.
public sealed class EnvironmentDeliverySecrets(TenantContext tenant):IDeliverySecretResolver {
 public Task<byte[]> ResolveAsync(string reference,CancellationToken ct) {
  ct.ThrowIfCancellationRequested();tenant.Demand("destinations:deliver");DestinationManagement.Id(reference);
  string text=Environment.GetEnvironmentVariable("ROUTER_DELIVERY_KEYS_JSON")??throw new InvalidOperationException("DELIVERY_KEYS_MISSING");
  if(text.Length>131072)throw new InvalidOperationException("DELIVERY_KEYS_INVALID");
  try {
   using var json=JsonDocument.Parse(text,new JsonDocumentOptions{MaxDepth=3});
   var root=json.RootElement;if(root.ValueKind!=JsonValueKind.Object||root.EnumerateObject().Select(p=>p.Name).Distinct(StringComparer.Ordinal).Count()!=root.EnumerateObject().Count())throw new InvalidOperationException("DELIVERY_KEYS_INVALID");
   var scoped=root.GetProperty(tenant.TenantId);
   if(scoped.ValueKind!=JsonValueKind.Object||scoped.EnumerateObject().Select(p=>p.Name).Distinct(StringComparer.Ordinal).Count()!=scoped.EnumerateObject().Count())throw new InvalidOperationException("DELIVERY_KEYS_INVALID");
   byte[] key=Convert.FromBase64String(scoped.GetProperty(reference).GetString()??"");
   if(key.Length is <24 or >64){System.Security.Cryptography.CryptographicOperations.ZeroMemory(key);throw new InvalidOperationException("DELIVERY_KEYS_INVALID");}
   return Task.FromResult(key);
  }catch(Exception e)when(e is JsonException or KeyNotFoundException or FormatException){throw new InvalidOperationException("DELIVERY_KEYS_INVALID");}
 }
}
