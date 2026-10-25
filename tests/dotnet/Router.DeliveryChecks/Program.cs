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
    return issued.CopyWithPrivateKey(key);
}
var body=Encoding.UTF8.GetBytes("{\"synthetic\":true}");var signingKey=RandomNumberGenerator.GetBytes(32);
async Task Probe(string hostname,bool trusted,bool expired,int status,bool expected) {
    using var cert=Certificate(hostname,expired);
    using var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
    using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(8));
    string receipt="";int connections=0,resolutions=0;
    var server=Task.Run(async()=> {
        try {
            using var client=await listener.AcceptTcpClientAsync(timeout.Token);
            using var tls=new SslStream(client.GetStream());
            await tls.AuthenticateAsServerAsync(new SslServerAuthenticationOptions{ServerCertificate=cert,EnabledSslProtocols=SslProtocols.Tls12|SslProtocols.Tls13},timeout.Token);
            using var bytes=new MemoryStream();var one=new byte[1];int end=-1;
            while(await tls.ReadAsync(one,timeout.Token)>0) {
                bytes.WriteByte(one[0]);receipt=Encoding.UTF8.GetString(bytes.ToArray());
                if(end<0)end=receipt.IndexOf("\r\n\r\n",StringComparison.Ordinal);
                if(end>=0&&bytes.Length>=end+4+body.Length)break;
                if(bytes.Length>8192)throw new Exception("fixture request limit");
            }
            await tls.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 {status} Fixture\r\nContent-Length: 0\r\nLocation: https://other.fixture.test/\r\nConnection: close\r\n\r\n"),timeout.Token);
        } catch(Exception e) when(e is AuthenticationException or IOException or OperationCanceledException) { }
    });
    var trust=new X509ChainPolicy{TrustMode=X509ChainTrustMode.CustomRootTrust,RevocationMode=X509RevocationMode.NoCheck};
    if(trusted)trust.CustomTrustStore.Add(ca);
    using var transport=new SafeWebhookTransport((host,ct)=>{resolutions++;return Task.FromResult(new[]{IPAddress.Parse("93.184.216.34")});},async(endpoint,ct)=> {
        Check(endpoint.Address.Equals(IPAddress.Parse("93.184.216.34"))&&endpoint.Port==443,"validated address passed to connector");connections++;
        var tcp=new TcpClient();try{await tcp.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port,ct);return tcp.GetStream();}catch{tcp.Dispose();throw;}
    },trust);
    bool success=false;try {success=await transport.SendAsync(new Uri("https://delivery.fixture.test/callback"),"wh_synthetic",body,signingKey,timeout.Token);}catch(HttpRequestException){}
    await server;
    Check(success==expected,$"TLS hostname={hostname} trusted={trusted} expired={expired} status={status}");
    Check(resolutions==1&&connections==1,"one DNS resolution and one pinned connection; no redirects");
    if(expected) {
        Check(receipt.EndsWith(Encoding.UTF8.GetString(body),StringComparison.Ordinal),"real HTTPS sink received exact synthetic body");
        Check(receipt.Contains("X-Webhook-Signature-256: sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(signingKey,body)),StringComparison.Ordinal),"real HTTPS sink verified body signature");
        Check(receipt.Contains("X-Webhook-Delivery: wh_synthetic",StringComparison.Ordinal),"real HTTPS sink received delivery ID");
    }
}
await Probe("delivery.fixture.test",true,false,200,true);
await Probe("wrong.fixture.test",true,false,200,false);
await Probe("delivery.fixture.test",false,false,200,false);
await Probe("delivery.fixture.test",true,true,200,false);
await Probe("delivery.fixture.test",true,false,302,false);
int attempted=0;
using(var blocked=new SafeWebhookTransport((host,ct)=>Task.FromResult(new[]{IPAddress.Parse("93.184.216.34"),IPAddress.Loopback}),(endpoint,ct)=>{attempted++;throw new Exception("must not connect");},null)) {
    try {await blocked.SendAsync(new Uri("https://delivery.fixture.test/"),"wh_synthetic",body,signingKey,CancellationToken.None);throw new Exception("private DNS accepted");}catch(HttpRequestException){}
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
