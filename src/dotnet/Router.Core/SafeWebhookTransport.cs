using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
namespace Router.Core;

// No proxy/redirects. DNS is validated and connected directly, preserving the URI
// hostname for standard TLS certificate verification. No user-selected ConnectCallback.
public sealed class SafeWebhookTransport:IWebhookTransport,IDisposable {
    private readonly HttpClient http;
    public SafeWebhookTransport() {
        var handler=new SocketsHttpHandler {AllowAutoRedirect=false,UseProxy=false,ConnectTimeout=TimeSpan.FromSeconds(3),PooledConnectionLifetime=TimeSpan.Zero,MaxConnectionsPerServer=2};
        handler.ConnectCallback=async(context,ct)=> {
            if(context.DnsEndPoint.Port!=443)throw new HttpRequestException("DESTINATION_PORT_DENIED");
            var addresses=await Dns.GetHostAddressesAsync(context.DnsEndPoint.Host,ct);
            if(addresses.Length is 0 or >16||addresses.Any(a=>!IsPublic(a)))throw new HttpRequestException("DESTINATION_ADDRESS_DENIED");
            var address=addresses[0];var socket=new Socket(address.AddressFamily,SocketType.Stream,ProtocolType.Tcp);
            try {await socket.ConnectAsync(new IPEndPoint(address,443),ct);return new NetworkStream(socket,ownsSocket:true);}catch{socket.Dispose();throw;}
        };
        http=new(handler){Timeout=TimeSpan.FromSeconds(10)};
    }
    public static void ValidateEndpoint(Uri endpoint) {
        if(!endpoint.IsAbsoluteUri||endpoint.Scheme!="https"||endpoint.Port!=443||endpoint.UserInfo.Length!=0||endpoint.Fragment.Length!=0||endpoint.Query.Length!=0||endpoint.IsLoopback||IPAddress.TryParse(endpoint.Host,out _)||endpoint.HostNameType!=UriHostNameType.Dns)throw new InvalidOperationException("DESTINATION_URL_DENIED");
    }
    public static bool IsPublic(IPAddress address) {
        if(address.AddressFamily==AddressFamily.InterNetworkV6&&address.ScopeId!=0)return false;
        if(address.IsIPv4MappedToIPv6)address=address.MapToIPv4();var b=address.GetAddressBytes();
        if(b.Length==4) {
            return !(b[0] is 0 or 10 or 127||b[0]>=224||b[0]==100&&b[1] is >=64 and <=127||b[0]==169&&b[1]==254||b[0]==172&&b[1] is >=16 and <=31||b[0]==192&&(b[1] is 0 or 168||b[1]==88&&b[2]==99)||b[0]==198&&(b[1] is 18 or 19||b[1]==51&&b[2]==100)||b[0]==203&&b[1]==0&&b[2]==113);
        }
        // Conservative global-unicast allowlist; excludes transition/special/docs ranges.
        return b.Length==16&&(b[0]&0xe0)==0x20&&!(b[0]==0x3f&&b[1]==0xff&&(b[2]&0xf0)==0)&&!(b[0]==0x20&&b[1]==0x02)&&!(b[0]==0x20&&b[1]==0x01&&(b[2]<2||b[2]==0x0d&&b[3]==0xb8));
    }
    public static HttpRequestMessage CreateSignedRequest(Uri endpoint,string eventId,byte[] payload,byte[] signingKey) {
        ValidateEndpoint(endpoint);if(payload.Length>65536||signingKey.Length is <24 or >64||eventId.Length is 0 or >128||eventId.Any(c=>!char.IsAsciiLetterOrDigit(c)&&c!='_'))throw new InvalidOperationException("DELIVERY_LIMIT");
        var request=new HttpRequestMessage(HttpMethod.Post,endpoint){Content=new ByteArrayContent(payload)};
        request.Content.Headers.ContentType=new MediaTypeHeaderValue("application/json");
        request.Headers.Add("X-Webhook-Delivery",eventId);
        request.Headers.Add("X-Webhook-Signature-256","sha256="+Convert.ToHexStringLower(HMACSHA256.HashData(signingKey,payload)));
        return request;
    }
    public async Task<bool> SendAsync(Uri endpoint,string eventId,byte[] payload,byte[] signingKey,CancellationToken ct) {
        using var request=CreateSignedRequest(endpoint,eventId,payload,signingKey);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,ct);
        return response.IsSuccessStatusCode;
    }
    public void Dispose()=>http.Dispose();
}
