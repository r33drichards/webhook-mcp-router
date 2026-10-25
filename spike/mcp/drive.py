import json, subprocess, sys, selectors, time
command=sys.argv[1:]
p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ)
def request(value):
 p.stdin.write(json.dumps(value)+'\n');p.stdin.flush()
 if not sel.select(60):
  p.kill(); raise AssertionError('response timeout: '+p.stderr.read())
 line=p.stdout.readline()
 if not line:
  raise AssertionError('no response; stderr='+p.stderr.read())
 answer=json.loads(line);print(json.dumps(answer,sort_keys=True),flush=True);return answer
try:
 r=request({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'synthetic','version':'0'}}})
 assert r['result']['serverInfo']['name']=='synthetic-event-spike'
 assert 'events' not in r['result']['capabilities'], 'Unexpected top-level events capability'
 assert r['result']['capabilities']['extensions']['example.invalid/events']=={}
 p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
 r=request({'jsonrpc':'2.0','id':2,'method':'events/list','params':{}})
 assert r['result']['events'][0]['name']=='webhook.received'
 r=request({'jsonrpc':'2.0','id':3,'method':'events/subscribe','params':{'name':'webhook.received','arguments':{},'delivery':{'mode':'webhook','url':'https://synthetic.invalid/callback','secret':'SYNTHETIC_NOT_A_REAL_SECRET'}}})
 assert r['result']['id']=='sub_synthetic' and r['result']['cursor'] is None
 assert 'SYNTHETIC_NOT_A_REAL_SECRET' not in json.dumps(r)
 print('ASSERTIONS_PASS: initialize, custom events/list, custom events/subscribe, null cursor, secret omitted, capabilities gap',flush=True)
finally:
 p.stdin.close()
 try:p.wait(timeout=5)
 except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
 print('PROCESS_EXIT:',p.returncode,flush=True)
 print('STDERR:',p.stderr.read(),flush=True)
