"""Offline credential-scope and cleanup tests; no remote requests."""
import contextlib,importlib.util,io,json,os,pathlib,tempfile,unittest,urllib.error
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)

def fake_api(values,updates):
    def query(document,variables):
        if document==edge.ENV_QUERY:
            return {'getDeployApp':{'id':edge.APP_ID,'name':'webhook-mcp-router','url':'https://owned.wasmer.app','envVars':{'edges':[{'node':{'name':n,'sensitive':v['sensitive']}} for n,v in values.items() if n in variables['names']],'pageInfo':{'hasNextPage':False}}}}
        if document==edge.UPDATE_QUERY:
            assert variables['input']['appId']==edge.APP_ID
            for item in variables['input']['envVars']:
                updates.append(item.copy())
                if item.get('delete'):values.pop(item['name'],None)
                else:values[item['name']]={'value':item['value'],'sensitive':item['sensitive']}
            return {'updateEnvVars':{'success':True}}
        return {'redeployActiveAppVersion':{'app':{'id':edge.APP_ID}}}
    return query

class LifecycleTests(unittest.TestCase):
    def test_readiness_diagnostics_never_emit_echoed_secrets(self):
        secret='synthetic-private-token'
        body=('<html>Bad Gateway Authorization: Bearer '+secret+'</html>').encode()
        response=urllib.error.HTTPError('https://owned.wasmer.app',502,secret,{'Authorization':secret},io.BytesIO(body))
        with patch.object(edge.OPENER,'open',side_effect=response):
            ready,diagnostic=edge.readiness_probe(object())
        self.assertFalse(ready)
        self.assertEqual(diagnostic['status'],502)
        self.assertEqual(diagnostic['category'],'http_error')
        self.assertEqual(diagnostic['body']['recognized_errors'],['bad gateway'])
        self.assertNotIn(secret,json.dumps(diagnostic))
        self.assertNotIn('Authorization',json.dumps(diagnostic))

    def test_readiness_bounds_and_rpc_errors(self):
        for body,category in [(b'x'*65538,'response_limit'),(b'not json','invalid_json'),
                              (b'{"error":{"message":"private"}}','rpc_error'),
                              (b'{"result":null}','missing_result')]:
            response=io.BytesIO(body);response.status=200
            with patch.object(edge.OPENER,'open',return_value=response):
                ready,diagnostic=edge.readiness_probe(object())
            self.assertFalse(ready);self.assertEqual(diagnostic['category'],category)
            self.assertNotIn('private',json.dumps(diagnostic))
            self.assertLessEqual(diagnostic['body']['bytes_read'],65537)

    def test_readiness_network_failure_is_category_only(self):
        with patch.object(edge.OPENER,'open',side_effect=urllib.error.URLError(TimeoutError('private URL/token'))):
            ready,diagnostic=edge.readiness_probe(object())
        self.assertFalse(ready);self.assertEqual(diagnostic,{'status':None,'category':'timeout'})

    def test_cleanup_deletes_only_approved_names_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            state=pathlib.Path(directory)/'state.json';state.write_text(json.dumps({'secrets_attempted':True,'url':'https://owned.wasmer.app'}))
            values={n:{'sensitive':True,'value':'synthetic'} for n in (*edge.NAMES,'UNRELATED')};updates=[]
            with patch.object(edge,'STATE',state),patch.object(edge,'graphql',fake_api(values,updates)),patch.object(edge,'cli',return_value='{}'),patch.object(edge.OPENER,'open',side_effect=urllib.error.HTTPError('https://owned.wasmer.app',500,'closed',{},None)),contextlib.redirect_stdout(io.StringIO()) as output:
                edge.cleanup()
            self.assertEqual(set(values),{'UNRELATED'})
            self.assertEqual(updates,[{'name':n,'delete':True} for n in edge.NAMES])
            self.assertIn('live rejection',output.getvalue())

    def test_missing_state_performs_no_remote_action(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(edge,'STATE',pathlib.Path(directory)/'absent'),patch.object(edge,'graphql') as api,patch.object(edge,'cli') as cli,contextlib.redirect_stdout(io.StringIO()):
            edge.cleanup();api.assert_not_called();cli.assert_not_called()

    def test_null_metadata_is_not_empty_inventory(self):
        with patch.object(edge,'graphql',return_value={'getDeployApp':None}):
            with self.assertRaises(RuntimeError):edge.secret_names()

    def test_unapproved_name_and_nonsensitive_write_rejected(self):
        with patch.object(edge,'graphql') as api:
            for update in [{'name':'UNRELATED','delete':True},{'name':edge.NAMES[0],'value':'synthetic','sensitive':False}]:
                with self.assertRaises(RuntimeError):edge.update_env([update])
            api.assert_not_called()

    def test_secret_transfer_is_sensitive_api_only_and_never_logged_or_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);(root/'deploy').mkdir();(root/'deploy/app.yaml').write_text('env:\n  POC_STATE_DIR: /state\n');(root/'deploy/wasmer.toml').write_text('version = "0.0.1"\n')
            supplied={n:'synthetic-'+n for n in edge.NAMES};supplied.update(WASMER_TOKEN='synthetic-account-token',POC_DNS_SERVER='127.0.0.1:5353',GITHUB_ENV=str(root/'env'))
            values={};updates=[]
            def cli(*args,**kwargs):
                self.assertNotIn('secret',args)
                self.assertTrue(all(supplied[n] not in ' '.join(args) for n in edge.NAMES))
                return json.dumps({'id':edge.APP_ID,'url':'https://owned.wasmer.app'}) if args[:2]==('app','get') else '{}'
            response=io.BytesIO(b'{"result":{}}');response.status=200
            previous=os.getcwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ,supplied),patch.object(edge,'STATE',root/'state'),patch.object(edge,'cli',cli),patch.object(edge,'graphql',fake_api(values,updates)),patch.object(edge.OPENER,'open',return_value=response),contextlib.redirect_stdout(io.StringIO()) as output:
                    edge.deploy()
            finally:os.chdir(previous)
            self.assertEqual(updates,[{'name':n,'value':supplied[n],'sensitive':True} for n in edge.NAMES])
            for name in edge.NAMES:
                self.assertNotIn(supplied[name],output.getvalue()+(root/'state').read_text()+(root/'env').read_text()+(root/'deploy/app.yaml').read_text())
            self.assertNotIn(' value',edge.ENV_QUERY)

if __name__=='__main__':unittest.main()
