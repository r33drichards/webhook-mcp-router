"""Read-only exact active package audit. No deploy, secret values, or mutations."""
import importlib.util,json,pathlib,re
spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)
QUERY='''query AuditWCGI($owner:String!,$name:String!) {
 getDeployApp(owner:$owner,name:$name) { id name activeVersion {
  id isActive url permalink jsonConfig
  sourcePackageVersion { version manifest webcGenerationErrors isCorrupt
   webc {version manifest webcSha256} webcV3 {version manifest webcSha256}
   modules {name source abi} commands {command}
  }
  sourcePackageRelease {tag webc {version manifest webcSha256} webcV3 {version manifest webcSha256}}
 }}
}'''
def text(value):
    return value if isinstance(value,str) and len(value)<=256 and re.fullmatch(r'[a-zA-Z0-9_./:@=+\- ]*',value) else '<omitted>'
def manifest(value):
    if isinstance(value,str):value=json.loads(value)
    if not isinstance(value,dict):raise ValueError('invalid manifest')
    commands=value.get('commands',{})
    result={'entrypoint':text(value.get('entrypoint')),'commands':{},'atom_names':list(value.get('atoms',{}))}
    for name,command in commands.items():
        annotations=command.get('annotations',{})
        wasi=annotations.get('wasi',{});wcgi=annotations.get('wcgi',{})
        result['commands'][text(name)]={'runner':text(command.get('runner')),
            'annotation_keys':[text(k) for k in annotations],
            'wasi_atom':text(wasi.get('atom')),'wasi_entrypoint':text(wasi.get('entrypoint')),
            'wcgi_dialect':text(wcgi.get('dialect'))}
    return result

def main():
    app=edge.graphql(QUERY,{'owner':'r33drichards','name':'webhook-mcp-router'})['getDeployApp']
    if not app or app['id']!=edge.APP_ID:raise ValueError('canonical app mismatch')
    version=app['activeVersion'];config=json.loads(version['jsonConfig'])
    output={'app_id':app['id'],'version_id':version['id'],'is_active':version['isActive'],
            'version_url':text(version['url']),'permalink':text(version['permalink']),
            'config_keys':[text(k) for k in config], 'package':text(config.get('package')),
            'package_metadata':{}}
    for field in ('sourcePackageVersion','sourcePackageRelease'):
        package=version.get(field)
        if not package:continue
        item={'version_or_tag':text(package.get('version',package.get('tag'))),
              'is_corrupt':package.get('isCorrupt'),
              'generation_error_present':bool(package.get('webcGenerationErrors'))}
        for fmt in ('webc','webcV3'):
            webc=package.get(fmt)
            if webc:item[fmt]={'version':webc['version'],'sha256':text(webc['webcSha256']),
                                'manifest':manifest(webc['manifest'])}
        item['modules']=[{k:text(m.get(k)) for k in ('name','source','abi')} for m in package.get('modules',[])]
        output['package_metadata'][field]=item
    print(json.dumps(output,indent=2))
if __name__=='__main__':
    try:main()
    except Exception:
        print('FAIL read-only package audit; response bodies and configuration values withheld')
        raise SystemExit(1)
