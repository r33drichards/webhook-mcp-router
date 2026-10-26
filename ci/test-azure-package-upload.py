from pathlib import Path
import importlib.util,tempfile,hashlib
s=importlib.util.spec_from_file_location('upload',Path(__file__).with_name('azure-package-upload.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Client:
 def __init__(self,exists=False,corrupt=False):self.exists=exists;self.corrupt=corrupt;self.calls=[]
 def upload_blob(self,data,**kwargs):
  self.calls.append(kwargs)
  assert kwargs=={'overwrite':False,'if_none_match':'*'}
  if self.exists:raise RuntimeError('precondition failed')
  self.data=data
 def download_blob(self):return self
 def chunks(self):yield b'wrong' if self.corrupt else self.data
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.zip';p.write_bytes(b'synthetic package bytes');digest=hashlib.sha256(p.read_bytes()).hexdigest()
 c=Client();assert m.publish(c,p,digest).endswith(digest+'.zip')
 for c,h in [(Client(True),digest),(Client(corrupt=True),digest),(Client(),'0'*64),(Client(),'../other')]:
  try:m.publish(c,p,h)
  except (ValueError,RuntimeError):pass
  else:raise AssertionError('Unsafe upload accepted')
print('PASS 5 package-upload contract checks (fake client; not Azure transport)')
