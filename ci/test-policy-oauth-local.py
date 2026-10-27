"""Compile real policy OAuth metadata/preflight code; no credentials or network."""
import json,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1];sdk=root/'.tools/dotnet'
with tempfile.TemporaryDirectory() as folder:
 p=pathlib.Path(folder)
 (p/'Test.cs').write_text('''using System;using System.Linq;using System.Collections.Generic;using System.Text.Json.Nodes;using Router.Mcp;using Router.Core;
class Test {static void Main(){int checks=0;void Check(bool ok){if(!ok)throw new Exception("OAuth contract failure");checks++;}
var read=new TenantContext("tenant-a","client-a",new[]{"router:read","policies:read"});
Check(PolicyOAuth.RequireScopes(read,"policies_get")==null);
foreach(var name in new[]{"policies_apply","policies_validate","policies_preview"}) {
 var r=PolicyOAuth.RequireScopes(read,name)!;
 Check(r["isError"]!.GetValue<bool>());
 var h=r["_meta"]!["mcp/www_authenticate"]![0]!.GetValue<string>();
 Check(h.Contains("error=\\\"insufficient_scope\\\"")&&h.Contains(PolicyOAuth.Metadata));
 Check(!h.Contains("tenant-a")&&!h.Contains("client-a")&&!h.Contains("\\r")&&!h.Contains("\\n"));
}
Check(PolicyOAuth.RequireScopes(read,"attacker\\r\\nInjected")==null);
var tester=new TenantContext("tenant-a","client-a",new[]{"router:read","policies:test"});
Check(PolicyOAuth.RequireScopes(tester,"policies_validate")==null);
Check(PolicyOAuth.RequireScopes(tester,"policies_preview")!=null);
var previewer=new TenantContext("tenant-a","client-a",new[]{"router:read","policies:test","destinations:read"});
Check(PolicyOAuth.RequireScopes(previewer,"policies_preview")==null);
Check(PolicyOAuth.RequireScopes(previewer,"policies_apply")!=null);
foreach(var name in new[]{"policies_get","policies_validate","policies_preview","policies_apply"}) {
 var tool=new JsonObject{["name"]=name};PolicyOAuth.Annotate(tool);
 var result=new JsonObject{["tools"]=new JsonArray(tool)};PolicyOAuth.MirrorSchemes(result);
 Check(tool["securitySchemes"]!.ToJsonString()==tool["_meta"]!["securitySchemes"]!.ToJsonString());
 Check(tool["securitySchemes"]![0]!["type"]!.GetValue<string>()=="oauth2");
 Check(!tool.ToJsonString().Contains("noauth")&&!tool.ToJsonString().Contains("destinations:write"));
}
var unrelated=new JsonObject{["name"]="destinations_register"};PolicyOAuth.Annotate(unrelated);Check(unrelated["_meta"]==null);
Console.WriteLine($"PASS {checks} compiled policy OAuth preflight/metadata checks; SDK wire coverage requires CI");}}
''')
 (p/'Global.cs').write_text('global using System; global using System.Linq; global using System.Collections.Generic;')
 refs=sorted((sdk/'packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
 subprocess.run([str(sdk/'dotnet'),str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-nullable:enable','-warnaserror','-target:exe',f'-out:{p}/Test.dll',*[f'-r:{r}' for r in refs],str(p/'Global.cs'),str(p/'Test.cs'),str(root/'src/dotnet/Router.Mcp/PolicyOAuth.cs'),str(root/'src/dotnet/Router.Core/TenantContext.cs')],check=True)
 (p/'Test.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}}))
 subprocess.run([str(sdk/'dotnet'),str(p/'Test.dll')],check=True)
