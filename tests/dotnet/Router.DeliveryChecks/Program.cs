using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Router.Core;

void Check(bool value,string name) {if(!value)throw new Exception(name);Console.WriteLine("PASS "+name);}
using var caKey=RSA.Create(2048);
var caRequest=new CertificateRequest("CN=Ephemeral router fixture CA",caKey,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
caRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(true,false,0,true));
caRequest.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign,true));
using var ca=caRequest.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-2),DateTimeOffset.UtcNow.AddDays(2));
X509Certificate2 Certificate(string hostname,bool expired=false) {
    using var key=RSA.Create(2048);
    var request=new CertificateRequest("CN="+hostname,key,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
    var san=new SubjectAlternativeNameBuilder();san.AddDnsName(hostname);request.CertificateExtensions.Add(san.Build());
    request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false,false,0,true));
    request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(new OidCollection{new Oid("1.3.6.1.5.5.7.3.1")},true));
    using var issued=request.Create(ca,DateTimeOffset.UtcNow.AddDays(-1),expired?DateTimeOffset.UtcNow.AddHours(-1):DateTimeOffset.UtcNow.AddDays(1),RandomNumberGenerator.GetBytes(16));
    using var withKey=issued.CopyWithPrivateKey(key);
    // Windows Schannel needs an imported certificate/private-key association.
    return X509CertificateLoader.LoadPkcs12(withKey.Export(X509ContentType.Pkcs12),null);
}
var body=Encoding.UTF8.GetBytes("{\"repository\":{\"id\":961207108,\"full_name\":\"r33drichards/mcp-js\"},\"action\":\"labeled\",\"label\":{\"name\":\"review\"}}");var signingKey=RandomNumberGenerator.GetBytes(32);
async Task Probe(string hostname,bool trusted,bool expired,int status,bool expected) {
    using var cert=Certificate(hostname,expired);
    using var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
    using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(8));
    byte[] expectedBody=body;string receipt="";int connections=0,resolutions=0;
    var server=Task.Run(async()=> {
        try {
            using var client=await listener.AcceptTcpClientAsync(timeout.Token);
            using var tls=new SslStream(client.GetStream());
            await tls.AuthenticateAsServerAsync(new SslServerAuthenticationOptions{ServerCertificate=cert,EnabledSslProtocols=SslProtocols.Tls12|SslProtocols.Tls13},timeout.Token);
            using var bytes=new MemoryStream();var one=new byte[1];int end=-1;
            while(await tls.ReadAsync(one,timeout.Token)>0) {
                bytes.WriteByte(one[0]);receipt=Encoding.UTF8.GetString(bytes.ToArray());
                if(end<0)end=receipt.IndexOf("\r\n\r\n",StringComparison.Ordinal);
                if(end>=0&&bytes.Length>=end+4+expectedBody.Length)break;
                if(bytes.Length>8192)throw new Exception("fixture request limit");
            }
            await tls.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 {status} Fixture\r\nContent-Length: 0\r\nLocation: https://other.fixture.test/\r\nConnection: close\r\n\r\n"),timeout.Token);
        } catch(Exception e) when(e is AuthenticationException or IOException or OperationCanceledException) {Console.WriteLine("FIXTURE TLS server: "+e.GetType().Name+": "+e.Message);}
    });
    var trust=new X509ChainPolicy{TrustMode=X509ChainTrustMode.CustomRootTrust,RevocationMode=X509RevocationMode.NoCheck};
    if(trusted)trust.CustomTrustStore.Add(ca);
    using var transport=new SafeWebhookTransport((host,ct)=>{resolutions++;return Task.FromResult(new[]{IPAddress.Parse("93.184.216.34")});},async(endpoint,ct)=> {
        Check(endpoint.Address.Equals(IPAddress.Parse("93.184.216.34"))&&endpoint.Port==443,"validated address passed to connector");connections++;
        var tcp=new TcpClient();try{await tcp.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port,ct);return tcp.GetStream();}catch{tcp.Dispose();throw;}
    },trust);
    bool success=false;
    if(expected&&args.Length==2) {
        var tenant=new TenantContext("tenant-fixture","fixture",["destinations:deliver"]);
        var store=new FixtureOutbox();int signals=0;
        var opa=new OpaEvaluator(args[0],args[1]);
        var ingress=new GenericIngestion(new FixtureRegistry(),new FixtureMetadata(),store,opa,tenant,signingKey,"mcp-js-github",961207108,ct=>{signals++;return Task.CompletedTask;});
        string signature="sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(signingKey,body));
        Check(await ingress.AcceptAsync(Guid.NewGuid().ToString(),"pull_request",body,signature,timeout.Token),"signed ingress through real OPA queues selected destination");
        Check(signals==1&&store.Item is not null,"committed selection signals dispatcher");
        expectedBody=Encoding.UTF8.GetBytes(store.Item!.Body);
        await new GenericDeliveryProcessor(new FixtureTarget(),new FixtureSecret(signingKey),store,tenant,transport).OnceAsync(timeout.Token);
        success=store.Completed;
        Check(success,"ingress OPA outbox dispatcher real TLS receipt completes delivery");
    } else try {success=await transport.SendAsync(new Uri("https://delivery.fixture.test/callback"),"wh_synthetic",body,signingKey,timeout.Token);}catch(HttpRequestException e){Console.WriteLine("FIXTURE TLS client: "+e.GetType().Name+": "+e.Message+"; "+e.InnerException?.Message);}
    await server;
    Check(success==expected,$"TLS hostname={hostname} trusted={trusted} expired={expired} status={status}");
    Check(resolutions==1&&connections==1,"one DNS resolution and one pinned connection; no redirects");
    if(expected) {
        Check(receipt.EndsWith(Encoding.UTF8.GetString(expectedBody),StringComparison.Ordinal),"real HTTPS sink received exact synthetic body");
        Check(receipt.Contains("X-Webhook-Signature-256: sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(signingKey,expectedBody)),StringComparison.Ordinal),"real HTTPS sink verified body signature");
        Check(receipt.Contains("X-Webhook-Delivery: wh_",StringComparison.Ordinal),"real HTTPS sink received delivery ID");
    }
}
await Probe("delivery.fixture.test",true,false,200,true);
await Probe("wrong.fixture.test",true,false,200,false);
await Probe("delivery.fixture.test",false,false,200,false);
await Probe("delivery.fixture.test",true,true,200,false);
await Probe("delivery.fixture.test",true,false,302,false);
int attempted=0;
using(var blocked=new SafeWebhookTransport((host,ct)=>Task.FromResult(new[]{IPAddress.Parse("93.184.216.34"),IPAddress.Loopback}),(endpoint,ct)=>{attempted++;throw new Exception("must not connect");},null)) {
    try {await blocked.SendAsync(new Uri("https://delivery.fixture.test/"),"wh_synthetic",body,signingKey,CancellationToken.None);throw new Exception("private DNS accepted");}catch(HttpRequestException e){Console.WriteLine("FIXTURE TLS client: "+e.GetType().Name+": "+e.Message+"; "+e.InnerException?.Message);}
    Check(attempted==0,"mixed public/private DNS blocked before any socket connection");
}
CryptographicOperations.ZeroMemory(signingKey);

var previousKeys=Environment.GetEnvironmentVariable("ROUTER_DELIVERY_KEYS_JSON");
try {
    Environment.SetEnvironmentVariable("ROUTER_DELIVERY_KEYS_JSON",System.Text.Json.JsonSerializer.Serialize(new Dictionary<string,Dictionary<string,string>>{{"tenant-a",new(){{"key_alias",Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))}}}}));
    var secretResolver=new EnvironmentDeliverySecrets(new TenantContext("tenant-a","dispatcher",["destinations:deliver"]));
    var first=await secretResolver.ResolveAsync("key_alias",default);var second=await secretResolver.ResolveAsync("key_alias",default);
    Check(first.Length==32&&!ReferenceEquals(first,second),"protected configuration returns fresh owned signing buffers");
    CryptographicOperations.ZeroMemory(first);CryptographicOperations.ZeroMemory(second);
    try {await new EnvironmentDeliverySecrets(new TenantContext("tenant-b","dispatcher",["destinations:deliver"])).ResolveAsync("key_alias",default);throw new Exception("cross tenant secret accepted");}catch(InvalidOperationException){Console.WriteLine("PASS other tenant signing key denied");}
    Environment.SetEnvironmentVariable("ROUTER_DELIVERY_KEYS_JSON","{\"tenant-a\":{},\"tenant-a\":{}}");
    try {await secretResolver.ResolveAsync("key_alias",default);throw new Exception("duplicate secret mapping accepted");}catch(InvalidOperationException){Console.WriteLine("PASS ambiguous secret mapping denied");}
} finally {Environment.SetEnvironmentVariable("ROUTER_DELIVERY_KEYS_JSON",previousKeys);}

sealed class FixtureRegistry:IRegistrationReader {
 public Task<RegistrationSnapshot> SnapshotAsync(string owner,CancellationToken ct)=>Task.FromResult(new RegistrationSnapshot([new("trial",File.ReadAllText("policies/trial/mcp-js-review.rego"))],[]));
}
sealed class FixtureMetadata:IDestinationReader {
 public Task<IReadOnlyList<RegisteredDestination>> SnapshotAsync(string owner,CancellationToken ct)=>Task.FromResult<IReadOnlyList<RegisteredDestination>>([new(owner,"fixture","Synthetic",["review"])]);
}
sealed class FixtureTarget:IDestinationResolver {
 public Task<ProtectedDestination?> ResolveAsync(string tenant,string id,CancellationToken ct)=>Task.FromResult<ProtectedDestination?>(tenant=="tenant-fixture"&&id=="fixture"?new(id,new Uri("https://delivery.fixture.test/callback"),"fixture_key"):null);
}
sealed class FixtureSecret(byte[] key):IDeliverySecretResolver {
 public Task<byte[]> ResolveAsync(string reference,CancellationToken ct)=>Task.FromResult(key.ToArray());
}
sealed class FixtureOutbox:IOutbox {
 public PendingDelivery? Item;public bool Completed;
 public Task<bool> AcceptAsync(string source,string id,string hash,IReadOnlyList<PendingDelivery> items,CancellationToken ct){Item=items.Single();return Task.FromResult(true);}
 public Task<ClaimedDelivery?> ClaimAsync(TimeSpan lease,CancellationToken ct)=>Task.FromResult(Item is null?null:new ClaimedDelivery(Item.Id,Item.SubscriptionId,Item.Body,Guid.NewGuid(),1));
 public Task<bool> CompleteAsync(string id,Guid lease,CancellationToken ct){Completed=true;return Task.FromResult(true);}
 public Task<bool> RetryAsync(string id,Guid lease,TimeSpan delay,int max,CancellationToken ct)=>Task.FromResult(true);
}
