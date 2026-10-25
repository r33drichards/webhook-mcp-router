using System.Collections.Frozen;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using Router.Core;
namespace Router.Auth;

public sealed record ServiceGrant(string ClientId,string Subject,string TenantId,string[] Scopes);
public interface ISigningKeys { Task<IReadOnlyList<SecurityKey>> GetAsync(bool refresh,CancellationToken ct); }
public sealed class TokenValidator {
    private readonly string issuer,audience;
    private readonly FrozenDictionary<string,ServiceGrant> grants;
    private readonly ISigningKeys keys;
    private readonly JsonWebTokenHandler handler=new() { MapInboundClaims=false,MaximumTokenSizeInBytes=16384 };
    public TokenValidator(string issuer,string audience,IEnumerable<ServiceGrant> grants,ISigningKeys keys) {
        if(!Uri.TryCreate(issuer,UriKind.Absolute,out var uri)||uri.Scheme!="https"||!string.IsNullOrEmpty(uri.Query)||!string.IsNullOrEmpty(uri.Fragment)||!string.IsNullOrEmpty(uri.UserInfo)||string.IsNullOrWhiteSpace(audience))throw new ArgumentException("ISSUER_CONFIG_INVALID");
        this.issuer=issuer;this.audience=audience;this.keys=keys;
        this.grants=grants.Select(g=>g with {Scopes=g.Scopes.ToArray()}).ToFrozenDictionary(g=>g.ClientId,StringComparer.Ordinal);
    }
    public async Task<TenantContext> ValidateAsync(string bearer,string requiredScope,CancellationToken ct=default) {
        ct.ThrowIfCancellationRequested();
        if(bearer.Length is 0 or >16384)throw new UnauthorizedAccessException("TOKEN_INVALID");
        var signingKeys=await keys.GetAsync(false,ct);
        TokenValidationResult result=await Validate(bearer,signingKeys);
        if(!result.IsValid && result.Exception is SecurityTokenSignatureKeyNotFoundException) {
            signingKeys=await keys.GetAsync(true,ct);result=await Validate(bearer,signingKeys);
        }
        ct.ThrowIfCancellationRequested();
        if(!result.IsValid || result.SecurityToken is not JsonWebToken token)throw new UnauthorizedAccessException("TOKEN_INVALID");
        // Reject ambiguous security claims even when a JWT parser would pick one value.
        using var payload=System.Text.Json.JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(token.EncodedPayload));
        var names=new HashSet<string>(StringComparer.Ordinal);
        foreach(var p in payload.RootElement.EnumerateObject())if(!names.Add(p.Name))throw new UnauthorizedAccessException("TOKEN_INVALID");
        string? Claim(string name)=>token.Claims.SingleOrDefault(c=>c.Type==name)?.Value;
        var client=Claim("azp");var subject=Claim("sub");
        if(client is null||!grants.TryGetValue(client,out var grant)||subject!=grant.Subject)throw new UnauthorizedAccessException("CLIENT_DENIED");
        var scopes=(Claim("scope")??"").Split(' ',StringSplitOptions.RemoveEmptyEntries).ToHashSet(StringComparer.Ordinal);
        var effective=grant.Scopes.Where(scopes.Contains);
        var context=new TenantContext(grant.TenantId,client,effective);context.Demand(requiredScope);return context;
    }
    private Task<TokenValidationResult> Validate(string token,IReadOnlyList<SecurityKey> signingKeys)=>handler.ValidateTokenAsync(token,new TokenValidationParameters {
        ValidateIssuer=true,ValidIssuer=issuer,ValidateAudience=true,ValidAudience=audience,
        ValidateLifetime=true,RequireExpirationTime=true,ClockSkew=TimeSpan.FromSeconds(30),
        RequireSignedTokens=true,ValidateIssuerSigningKey=true,IssuerSigningKeys=signingKeys,
        ValidAlgorithms=[SecurityAlgorithms.RsaSha256],ValidTypes=["JWT","at+jwt"],
        TryAllIssuerSigningKeys=false,IncludeTokenOnFailedValidation=false,LogTokenId=false
    });
}
