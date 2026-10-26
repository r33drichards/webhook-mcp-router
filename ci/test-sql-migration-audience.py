"""Compile/run the actual helper claim predicate without NuGet, credentials or SQL."""
import hashlib, json, os, re, subprocess, tempfile, shutil, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'tools/Router.SqlBootstrap/Program.cs').read_text()
predicate=re.search(r'Require\((c.GetProperty\("tid"\).*?)\);',source).group(1)
bootstrap=(root/'tools/Router.SqlBootstrap/Bootstrap.cs').read_text()
tenant=re.search(r'const string Tenant="([^"]+)"',bootstrap).group(1)
admin=re.search(r'const string Administrator="([^"]+)"',bootstrap).group(1)
# Literal expected identities also ensure tests do not follow a changed identity.
assert tenant=='0e4545fd-804f-4acb-ad41-f955e53645c1'
assert admin=='9e61efd9-e30d-4bda-93bb-c952234dfe67'
assert '(c.GetProperty("aud").GetString() is "https://database.windows.net" or "https://database.windows.net/")' in predicate
dotnet=shutil.which('dotnet') or str(root/'.tools/dotnet/dotnet')
sdk=Path(subprocess.check_output([dotnet,'--list-sdks'],text=True).split('[')[-1].split(']')[0]).parent
with tempfile.TemporaryDirectory(prefix='router-audience-') as tmp:
 p=Path(tmp)
 code='''using System;
using System.Text.Json;
class Bootstrap { public const string Tenant="TENANT"; public const string Administrator="ADMIN"; }
class Test {
 static bool Accept(object claims) { try { using var d=JsonDocument.Parse(JsonSerializer.Serialize(claims)); var c=d.RootElement; return PREDICATE; } catch { return false; } }
 static int Main() {
 int count=0; long future=DateTimeOffset.UtcNow.ToUnixTimeSeconds()+600;
 void Check(object value,bool expected) { if(Accept(value)!=expected)throw new Exception("CLAIM_CHECK_FAILED");count++; }
 foreach(var aud in new[]{"https://database.windows.net","https://database.windows.net/"}) Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud,exp=future},true);
 foreach(var aud in new string?[]{null,"","http://database.windows.net","https://database.windows.net//","https://database.windows.net/.default","https://database.windows.net.evil.invalid","https://database.windows.net@evil.invalid","https://database.windows.net:443/","https://DATABASE.windows.net/","https://database.windows.net/?x=1","https://database.windows.net/#x"," https://database.windows.net","https://database.windows.net/ ","https://management.azure.com/","https://graph.microsoft.com/"}) Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud,exp=future},false);
 foreach(var aud in new[]{"https://database.windows.net","https://database.windows.net/"}) {
 Check(new{tid="wrong",oid=Bootstrap.Administrator,aud,exp=future},false);
 Check(new{tid=Bootstrap.Tenant,oid="wrong",aud,exp=future},false);
 Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud,exp=DateTimeOffset.UtcNow.ToUnixTimeSeconds()+120},false);
 Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud,exp=0},false);
 }
 Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,exp=future},false);
 Check(new{tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud=new[]{"https://database.windows.net"},exp=future},false);
 Console.WriteLine($"PASS {count} compiled actual-helper claim predicate checks; no credentials/network/SQL");return 0;
 }
}
'''.replace('TENANT',tenant).replace('ADMIN',admin).replace('PREDICATE',predicate)
 (p/'Test.cs').write_text(code)
 refs=sorted((sdk/'packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
 assert refs
 subprocess.run([dotnet,str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-nullable:enable','-target:exe',f'-out:{p}/Test.dll',*[f'-r:{r}' for r in refs],str(p/'Test.cs')],check=True)
 (p/'Test.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}}))
 subprocess.run([dotnet,str(p/'Test.dll')],check=True)
 migrator=(root/'tools/Router.Migrator/Program.cs').read_text()
 mp=re.search(r'Require\((c.GetProperty\("tid"\).*?)\);',migrator).group(1)
 assert 'c.GetProperty("appid").GetString()==client' in mp
 assert 'c.GetProperty("oid").GetString()==principal' in mp
 mcode=code.replace(predicate,mp).replace('var c=d.RootElement;', 'var c=d.RootElement; var tenant=Bootstrap.Tenant; var principal=Bootstrap.Administrator; var client="synthetic-client";')
 mcode=mcode.replace('new{tid=', 'new{appid="synthetic-client",tid=')
 # Expiry checks belong to bootstrap; preserve migrator behavior in this narrow correction.
 mcode='\n'.join(line for line in mcode.split('\n') if 'exp=DateTimeOffset.UtcNow' not in line and 'aud,exp=0}' not in line)
 mcode=mcode.replace('Console.WriteLine($"PASS', 'Check(new{appid="wrong-client",tid=Bootstrap.Tenant,oid=Bootstrap.Administrator,aud="https://database.windows.net",exp=future},false);\n Console.WriteLine($"PASS').replace('actual-helper','actual-migrator')
 (p/'Test.cs').write_text(mcode)
 subprocess.run([dotnet,str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-nullable:enable','-target:exe',f'-out:{p}/Test.dll',*[f'-r:{r}' for r in refs],str(p/'Test.cs')],check=True)
 subprocess.run([dotnet,str(p/'Test.dll')],check=True)
