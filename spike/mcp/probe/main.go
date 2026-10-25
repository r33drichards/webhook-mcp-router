package main
import("fmt";"net";"net/http";"os";"os/exec";"time";"encoding/json";"io")
func main(){
 mode:="json";if len(os.Args)>1{mode=os.Args[1]}
 switch mode{
 case "json":var value map[string]any;if err:=json.NewDecoder(os.Stdin).Decode(&value);err!=nil{panic(err)};json.NewEncoder(os.Stdout).Encode(map[string]any{"received":value,"runtime":"go-wasip1"})
 case "outbound-http":
  c:=http.Client{Timeout:2*time.Second};r,err:=c.Get("http://"+os.Args[2]+"/synthetic")
  if err!=nil{fmt.Printf("OUTBOUND_HTTP_FAILED: %v\n",err);os.Exit(45)}
  defer r.Body.Close();b,err:=io.ReadAll(r.Body);if err!=nil||r.StatusCode!=200||string(b)!="synthetic-host-http"{fmt.Printf("OUTBOUND_HTTP_BAD_RESPONSE: status=%d body=%q error=%v\n",r.StatusCode,b,err);os.Exit(46)}
  fmt.Println("OUTBOUND_HTTP_PASS: synthetic-host-http")
 case "outbound-tcp":
  conn,err:=net.DialTimeout("tcp",os.Args[2],2*time.Second)
  if err!=nil{fmt.Printf("OUTBOUND_TCP_FAILED: %v\n",err);os.Exit(47)}
  defer conn.Close();conn.SetDeadline(time.Now().Add(2*time.Second))
  payload:=[]byte("synthetic-host-tcp");if _,err:=conn.Write(payload);err!=nil{panic(err)}
  b:=make([]byte,len(payload));if _,err:=io.ReadFull(conn,b);err!=nil{panic(err)}
  if string(b)!=string(payload){panic("bad echo")};fmt.Println("OUTBOUND_TCP_PASS: synthetic-host-tcp")
 case "http":l,err:=net.Listen("tcp","127.0.0.1:0");if err!=nil{fmt.Printf("HTTP_LISTEN_FAILED: %v\n",err);os.Exit(42)};defer l.Close();server:=&http.Server{Handler:http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){fmt.Fprint(w,"synthetic-ok")}),ReadHeaderTimeout:time.Second};go server.Serve(l);defer server.Close();c:=http.Client{Timeout:2*time.Second};r,err:=c.Get("http://"+l.Addr().String());if err!=nil{panic(err)};defer r.Body.Close();b,_:=io.ReadAll(r.Body);if string(b)!="synthetic-ok"{panic("bad response")};fmt.Println("HTTP_LOOPBACK_PASS: synthetic-ok")
 case "serve":l,err:=net.Listen("tcp","127.0.0.1:18089");if err!=nil{panic(err)};defer l.Close();fmt.Println("LISTENER_READY: 127.0.0.1:18089");server:=&http.Server{Handler:http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){fmt.Fprint(w,"synthetic-ok")}),ReadHeaderTimeout:time.Second};go server.Serve(l);time.Sleep(10*time.Second);server.Close()
 case "persist-write":if err:=os.WriteFile("/state/subscription.json",[]byte(`{"id":"sub_synthetic","mode":"dry_run"}`),0600);err!=nil{panic(err)};fmt.Println("PERSIST_WRITE_PASS")
 case "persist-read":b,err:=os.ReadFile("/state/subscription.json");if err!=nil{panic(err)};if string(b)!=`{"id":"sub_synthetic","mode":"dry_run"}`{panic("mismatch")};fmt.Println("PERSIST_READ_PASS:",string(b))
 case "exec-direct":cmd:=exec.Command("/state/router.wasm","json");cmd.Stdin=os.Stdin;cmd.Stdout=os.Stdout;cmd.Stderr=os.Stderr;err:=cmd.Run();fmt.Printf("EXEC_DIRECT_RESULT: %v\n",err);if err!=nil{os.Exit(43)}
 case "exec":out,err:=exec.Command("/synthetic-router.wasm").CombinedOutput();fmt.Printf("EXEC_RESULT: output=%q error=%v\n",out,err);if err!=nil{os.Exit(43)}
 }
}
