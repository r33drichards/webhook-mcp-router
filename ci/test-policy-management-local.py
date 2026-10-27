import json,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1];sdk=root/'.tools/dotnet'
with tempfile.TemporaryDirectory() as folder:
 p=pathlib.Path(folder);(p/'Global.cs').write_text('global using System; global using System.IO; global using System.Linq; global using System.Collections.Generic; global using System.Threading; global using System.Threading.Tasks; global using System.Net.Http;')
 refs=sorted((sdk/'packs/Microsoft.NETCore.App.Ref/10.0.13/ref/net10.0').glob('*.dll'))
 sources=sorted((root/'src/dotnet/Router.Core').glob('*.cs'))
 subprocess.run([str(sdk/'dotnet'),str(sdk/'sdk/10.0.402/Roslyn/bincore/csc.dll'),'-nologo','-nullable:enable','-warnaserror','-target:exe',f'-out:{p}/Test.dll',*[f'-r:{r}' for r in refs],str(p/'Global.cs'),*[str(s) for s in sources],str(root/'tests/dotnet/Router.PolicyChecks/Program.cs')],check=True)
 (p/'Test.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.13'}}}))
 subprocess.run([str(sdk/'dotnet'),str(p/'Test.dll'),str(root/'.tools/opa'),str(root/'policies/capabilities.json')],check=True)
