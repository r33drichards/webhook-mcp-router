using System.Security.Cryptography;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using Router.Auth;
const string issuer="https://issuer.example.invalid/realms/router",audience="router";
using var rsa=RSA.Create(2048);using var other=RSA.Create(2048);
var key=new RsaSecurityKey(rsa){KeyId="one"};var next=new RsaSecurityKey(other){KeyId="two"};
var source=new Keys(key,next);
var validator=new TokenValidator(issuer,audience,[new("client-a","service-a","tenant-a",["router:read"]),new("client-b","service-b","tenant-b",["router:read"])],source);
string Token(string client="client-a",string subject="service-a",string iss=issuer,string aud=audience,string scope="router:read",int expires=300,SecurityKey? signing=null,string? tenant=null)=>new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor {
 Issuer=iss,Audience=aud,IssuedAt=DateTime.UtcNow.AddMinutes(-10),NotBefore=DateTime.UtcNow.AddMinutes(-5),Expires=DateTime.UtcNow.AddSeconds(expires),
 Claims=new Dictionary<string,object>{{"azp",client},{"sub",subject},{"scope",scope},{"tenant",tenant??"attacker-tenant"}},SigningCredentials=new SigningCredentials(signing??key,SecurityAlgorithms.RsaSha256)
});
void Check(bool ok,string name){if(!ok)throw new Exception(name);Console.WriteLine("PASS "+name);}
async Task Deny(string token,string scope,string name) {try {await validator.ValidateAsync(token,scope);}catch(UnauthorizedAccessException){Console.WriteLine("PASS "+name);return;}throw new Exception(name);}
var a=await validator.ValidateAsync(Token(),"router:read");Check(a.TenantId=="tenant-a"&&a.ActorId=="client-a","trusted mapping ignores token tenant");
await Deny(Token(iss:"https://evil.example.invalid"),"router:read","wrong issuer");
await Deny(Token(aud:"another-api"),"router:read","wrong audience");
await Deny(Token(expires:-120),"router:read","expired");
await Deny(Token(client:"unknown"),"router:read","unknown client");
await Deny(Token(subject:"human-user"),"router:read","wrong service subject");
await Deny(Token(scope:""),"router:read","missing scope");
await Deny(Token(scope:"router:read policies:write"),"policies:write","token cannot exceed mapping grant");
Check((await validator.ValidateAsync(Token("client-b","service-b"),"router:read")).TenantId=="tenant-b","second tenant identity");
try {a.Match("tenant-b");throw new Exception("cross tenant accepted");}catch(UnauthorizedAccessException){Console.WriteLine("PASS cross tenant context denial");}
Check((await validator.ValidateAsync(Token(signing:next),"router:read")).TenantId=="tenant-a","key rotation refresh");
await Deny("not.a.jwt","router:read","malformed token");
var many=await Task.WhenAll(Enumerable.Range(0,16).Select(_=>validator.ValidateAsync(Token(signing:next),"router:read")));Check(many.All(x=>x.TenantId=="tenant-a"),"concurrent validation");
sealed class Keys(SecurityKey initial,SecurityKey next):ISigningKeys {
 private volatile bool rotated;
 public Task<IReadOnlyList<SecurityKey>> GetAsync(bool refresh,CancellationToken ct){ct.ThrowIfCancellationRequested();if(refresh)rotated=true;return Task.FromResult<IReadOnlyList<SecurityKey>>(rotated?[initial,next]:[initial]);}
}
