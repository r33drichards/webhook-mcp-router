"""Compile actual pure discovery source with installed official .NET; no network/auth."""
import json, pathlib, subprocess, tempfile
root=pathlib.Path(__file__).resolve().parents[1]
sdk=root/'.tools/dotnet'
with tempfile.TemporaryDirectory() as folder:
 p=pathlib.Path(folder)
 (p/'Test.cs').write_text('''using System; using System.Linq; using System.Text.Json; using Router.Functions;
class Test {static void Main(){
var j=JsonSerializer.SerializeToElement(McpDiscovery.Document());
void Check(bool ok){if(!ok)throw new Exception("Discovery contract failure");}
Check(j.GetProperty("resource").GetString()=="https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/api/mcp");
Check(j.GetProperty("authorization_servers")[0].GetString()=="https://keycloak-production-295b.up.railway.app/realms/webhook-router");
Check(j.GetProperty("authorization_servers").GetArrayLength()==1);
Check(j.GetProperty("scopes_supported").EnumerateArray().Select(x=>x.GetString()).SequenceEqual(new[]{"router:read","requests:read","destinations:read","policies:read","policies:test","policies:write"}));
Check(j.GetProperty("bearer_methods_supported")[0].GetString()=="header");
Check(!j.TryGetProperty("registration_endpoint",out _));
Check(McpDiscovery.Challenge=="Bearer resource_metadata=\\\"https://webhook-mcp-router-v2-f7076f8e38.azurewebsites.net/.well-known/oauth-protected-resource/api/mcp\\\", scope=\\\"router:read\\\"");
Check(!McpDiscovery.Challenge.Contains("\\r")&&!McpDiscovery.Challenge.Contains("\\n"));
Console.WriteLine("PASS 8 compiled discovery contract checks");}}
''')
 refs=sorted((sdk/'packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
 subprocess.run([str(sdk/'dotnet'),str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-nullable:enable','-target:exe',f'-out:{p}/Test.dll',*[f'-r:{r}' for r in refs],str(p/'Test.cs'),str(root/'src/dotnet/Router.Functions/McpDiscovery.cs')],check=True)
 (p/'Test.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}}))
 subprocess.run([str(sdk/'dotnet'),str(p/'Test.dll')],check=True)
