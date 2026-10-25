"""Offline checks of credential scope and cleanup orchestration; no service calls."""
import contextlib,importlib.util,io,json,os,pathlib,tempfile,unittest,urllib.error
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('edge',pathlib.Path(__file__).with_name('edge-lifecycle.py'))
edge=importlib.util.module_from_spec(spec);spec.loader.exec_module(edge)

class LifecycleTests(unittest.TestCase):
    def test_cleanup_deletes_only_approved_names_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            state=pathlib.Path(directory)/'state.json';state.write_text(json.dumps({'secrets_attempted':True,'url':'https://owned.wasmer.app'}))
            names=set(edge.NAMES)|{'UNRELATED'};calls=[]
            def cli(*args,**kwargs):
                calls.append(args)
                if args[:3]==('app','secret','delete'):names.remove(args[-1])
                if args[:3]==('app','secret','list'):return json.dumps([{'name':n} for n in names])
                return '{}'
            with patch.object(edge,'STATE',state),patch.object(edge,'cli',cli),patch.object(edge.OPENER,'open',side_effect=urllib.error.HTTPError('https://owned.wasmer.app',500,'closed',{},None)),contextlib.redirect_stdout(io.StringIO()) as output:
                edge.cleanup()
            self.assertEqual(names,{'UNRELATED'})
            self.assertEqual([c[-1] for c in calls if c[:3]==('app','secret','delete')],list(edge.NAMES))
            self.assertTrue(all('--all' not in c for c in calls))
            self.assertIn('live rejection',output.getvalue())

    def test_missing_state_performs_no_remote_action(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(edge,'STATE',pathlib.Path(directory)/'absent'),patch.object(edge,'cli') as cli,contextlib.redirect_stdout(io.StringIO()):
            edge.cleanup();cli.assert_not_called()

    def test_secret_transfer_uses_stdin_and_outputs_no_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);(root/'deploy').mkdir();(root/'deploy/app.yaml').write_text('env:\n  POC_STATE_DIR: /state\n');(root/'deploy/wasmer.toml').write_text('version = \"0.0.1\"\n')
            supplied={n:'synthetic-'+n for n in edge.NAMES};supplied.update(WASMER_TOKEN='synthetic-account-token',POC_DNS_SERVER='127.0.0.1:5353',GITHUB_ENV=str(root/'env'))
            names=set();transfers=[]
            def cli(*args,stdin=None):
                if args[:2]==('app','get'):return json.dumps({'url':'https://owned.wasmer.app'})
                if args[:3]==('app','secret','list'):return json.dumps([{'name':n} for n in names])
                if args[:3]==('app','secret','create'):
                    self.assertIn('/dev/stdin',args);transfers.append(stdin);names.update(edge.NAMES)
                self.assertTrue(all(supplied[n] not in ' '.join(args) for n in edge.NAMES))
                return '{}'
            response=io.BytesIO(b'{"result":{}}');response.status=200
            previous=os.getcwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ,supplied),patch.object(edge,'STATE',root/'state'),patch.object(edge,'cli',cli),patch.object(edge.OPENER,'open',return_value=response),contextlib.redirect_stdout(io.StringIO()) as output:
                    edge.deploy()
            finally:os.chdir(previous)
            self.assertEqual(len(transfers),1)
            for name in edge.NAMES:
                self.assertIn(name+'='+supplied[name],transfers[0])
                self.assertNotIn(supplied[name],output.getvalue()+ (root/'state').read_text()+(root/'env').read_text()+(root/'deploy/app.yaml').read_text())

if __name__=='__main__':unittest.main()
