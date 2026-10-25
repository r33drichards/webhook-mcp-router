using Microsoft.Data.SqlClient;
using Router.Core;
using Router.Storage;
using System.Text;
var name="router_synthetic_"+Guid.NewGuid().ToString("N");
var master=@"Server=(localdb)\MSSQLLocalDB;Integrated Security=true;Encrypt=false;Initial Catalog=master";
var connection=master.Replace("Initial Catalog=master","Initial Catalog="+name);
async Task Execute(string cs,string sql){await using var db=new SqlConnection(cs);await db.OpenAsync();await using var cmd=new SqlCommand(sql,db);await cmd.ExecuteNonQueryAsync();}
void Check(bool value,string name){if(!value)throw new Exception(name);Console.WriteLine("PASS "+name);}
async Task Deny(Func<Task> action,string name){try{await action();}catch(UnauthorizedAccessException){Console.WriteLine("PASS "+name);return;}throw new Exception(name);}
var ct=CancellationToken.None;
string[] scopes=["router:read","subscriptions:write","policies:write","requests:read","requests:append"];
var a=new TenantContext("tenant-a","client-a",scopes);var b=new TenantContext("tenant-b","client-b",scopes);
try {
 await Execute(master,"CREATE DATABASE ["+name+"]");await SqlMigration.ApplyAsync(connection);
 var wa=new SqlRegistrationWriter(connection,a);var wb=new SqlRegistrationWriter(connection,b);
 await wa.SavePolicyAsync(a.TenantId,new("same","package a"),ct);await wb.SavePolicyAsync(b.TenantId,new("same","package b"),ct);
 var ra=new SqlRegistrationReader(connection,a);var rb=new SqlRegistrationReader(connection,b);
 Check((await ra.SnapshotAsync(a.TenantId,ct)).Policies.Single().Source=="package a","SQL tenant policy isolation");
 await Deny(()=>ra.SnapshotAsync(b.TenantId,ct),"cross tenant registry read denied");
 await Deny(()=>wa.SavePolicyAsync(b.TenantId,new("same","evil"),ct),"cross tenant policy write denied");
 await wa.SaveSubscriptionAsync(new("sub_shared",a.TenantId,"webhook.received","{}","https://a.example.invalid","hash",DateTimeOffset.UtcNow.AddHours(1)),ct);
 await wb.SaveSubscriptionAsync(new("sub_shared",b.TenantId,"webhook.received","{}","https://b.example.invalid","hash",DateTimeOffset.UtcNow.AddHours(1)),ct);
 await Deny(()=>wa.DeleteSubscriptionAsync(b.TenantId,"sub_shared",ct),"cross tenant unsubscribe denied");
 Check((await rb.SnapshotAsync(b.TenantId,ct)).Subscriptions.Single().Callback=="https://b.example.invalid","callback isolation");
 var oa=new SqlOutbox(connection,a);var ob=new SqlOutbox(connection,b);var hash=new string('a',64);
 Check(await oa.AcceptAsync("github","same",hash,[new("event","sub_shared","{}")],ct),"tenant A receipt");
 Check(await ob.AcceptAsync("github","same",hash,[new("event","sub_shared","{}")],ct),"tenant B same delivery ID independent");
 Check(!await oa.AcceptAsync("github","same",hash,[],ct),"receipt duplicate");
 Check(await oa.AcceptAsync("other-source","same",hash,[],ct),"same delivery ID isolated by source");
 try {await oa.AcceptAsync("github","same",new string('b',64),[],ct);throw new Exception("conflicting body accepted");}
 catch(InvalidOperationException e)when(e.Message=="DELIVERY_ID_CONFLICT"){Console.WriteLine("PASS same delivery ID different body denied");}
 var repeated=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>oa.AcceptAsync("github","concurrent",hash,[],ct)));
 Check(repeated.Count(x=>x)==1,"concurrent SQL receipts accepted exactly once");
 var claim=(await oa.ClaimAsync(TimeSpan.FromSeconds(30),ct))!;
 Check(!await ob.CompleteAsync(claim.Id,claim.Lease,ct),"cross tenant outbox lease denied");
 Check(await oa.CompleteAsync(claim.Id,claim.Lease,ct),"own lease completion");
 Check(await ob.ClaimAsync(TimeSpan.FromSeconds(30),ct) is not null,"other tenant delivery preserved");
 var capture=new RequestCapture();var sample=capture.Capture("POST","accepted",Encoding.UTF8.GetBytes("{\"token\":\"secret\",\"message\":\"private\",\"number\":3}"),true,"issues");
 Check(sample.Redacted&&!sample.Payload!.Contains("secret")&&!sample.Payload.Contains("private"),"payload credentials and free text redacted");
 Check(capture.Capture("POST","failed",Encoding.UTF8.GetBytes("\"secret\""),true).Payload=="\"[REDACTED]\"","root string redaction");
 Check(!capture.Capture("POST","failed",Encoding.UTF8.GetBytes("{secret"),true).ValidJson,"malformed payload omitted");
 Check(capture.Capture("POST","rejected",new byte[65537],false).Truncated,"oversized payload omitted");
 Check(capture.Capture("POST","rejected",Encoding.UTF8.GetBytes("{}"),false).Payload is null,"unverified request has no example payload");
 var options=new CaptureOptions(MaxRows:3);var la=new SqlRequestLog(connection,a,options);var lb=new SqlRequestLog(connection,b,options);
 await la.AppendAsync(sample,ct);Check(await lb.FindAsync(sample.Id,ct) is null,"cross tenant request detail absent");
 for(int i=0;i<4;i++)await la.AppendAsync(capture.Capture("POST","failed",Encoding.UTF8.GetBytes("{}"),true),ct);
 var first=await la.ListAsync(2,null,ct);Check(first.Items.Count==2&&first.NextBefore is not null,"bounded log page");
 var second=await la.ListAsync(2,first.NextBefore,ct);Check(second.Items.Count==1&&second.NextBefore is null&&!first.Items.Select(x=>x.Sequence).Intersect(second.Items.Select(x=>x.Sequence)).Any(),"pagination and row cap");
 Check((await lb.ListAsync(100,null,ct)).Items.Count==0,"cross tenant list empty");
 var expired=capture.Capture("POST","accepted",Encoding.UTF8.GetBytes("{}"),true) with {Received=DateTimeOffset.UtcNow.AddDays(-8)};await la.AppendAsync(expired,ct);
 Check(await la.FindAsync(expired.Id,ct) is null,"expired log unreadable");
 var explorer=new RequestExplorer(new TenantContext("tenant-a","limited",["policies:write"]),la);await Deny(()=>explorer.ListAsync(),"explorer scope separate from policy permissions");
} finally {
 SqlConnection.ClearAllPools();await Execute(master,"IF DB_ID('"+name+"') IS NOT NULL BEGIN ALTER DATABASE ["+name+"] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE ["+name+"]; END");
}
