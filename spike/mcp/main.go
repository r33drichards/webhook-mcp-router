package main

import (
 "context"
 "encoding/json"
 "fmt"
 "io"
 "net"
 "net/http"
 "os"
 "os/exec"
 "time"

 "github.com/modelcontextprotocol/go-sdk/mcp"
)

type ListParams struct { mcp.ParamsBase }
type ListResult struct {
 mcp.ResultBase
 Events []map[string]any `json:"events"`
}
type SubscribeParams struct {
 mcp.ParamsBase
 Name string `json:"name"`
 Arguments map[string]any `json:"arguments"`
 Delivery struct { Mode, URL, Secret string } `json:"delivery"`
}
type SubscribeResult struct {
 mcp.ResultBase
 ID string `json:"id"`
 RefreshBefore string `json:"refreshBefore"`
 Cursor *string `json:"cursor"`
 Truncated bool `json:"truncated"`
}

func server() *mcp.Server {
 s:=mcp.NewServer(&mcp.Implementation{Name:"synthetic-event-spike",Version:"0.0.0"}, &mcp.ServerOptions{
  Capabilities: &mcp.ServerCapabilities{Extensions:map[string]any{"example.invalid/events":map[string]any{}}},
 })
 err:=mcp.AddReceivingCustomMethod(s,"events/list",func(ctx context.Context, ss *mcp.ServerSession, p *ListParams)(*ListResult,error){
  return &ListResult{Events:[]map[string]any{{"name":"webhook.received","delivery":[]string{"webhook"},"inputSchema":map[string]any{"type":"object"},"payloadSchema":map[string]any{"type":"object"}}}},nil
 })
 if err!=nil { panic(err) }
 err=mcp.AddReceivingCustomMethod(s,"events/subscribe",func(ctx context.Context, ss *mcp.ServerSession, p *SubscribeParams)(*SubscribeResult,error){
  if p.Name!="webhook.received" || p.Delivery.Mode!="webhook" || p.Delivery.URL!="https://synthetic.invalid/callback" { return nil,fmt.Errorf("synthetic-only subscription") }
  return &SubscribeResult{ID:"sub_synthetic",RefreshBefore:"2030-01-01T00:00:00Z",Cursor:nil,Truncated:false},nil
 })
 if err!=nil { panic(err) }
 return s
}

func main(){
 mode:="stdio";if len(os.Args)>1 {mode=os.Args[1]}
 switch mode {
 case "stdio":
  if err:=server().Run(context.Background(),&mcp.StdioTransport{});err!=nil {fmt.Fprintln(os.Stderr,err);os.Exit(1)}
 case "http-probe":
  l,err:=net.Listen("tcp","127.0.0.1:0")
  if err!=nil {fmt.Printf("HTTP_LISTEN_FAILED: %v\n",err);os.Exit(42)}
  defer l.Close()
  h:=mcp.NewStreamableHTTPHandler(func(r *http.Request)*mcp.Server{return server()},nil)
  hs:=&http.Server{Handler:h,ReadHeaderTimeout:time.Second}
  go hs.Serve(l);defer hs.Close()
  client:=http.Client{Timeout:2*time.Second}
  req,_:=http.NewRequest("POST","http://"+l.Addr().String()+"/mcp",nil)
  resp,err:=client.Do(req)
  if err!=nil {fmt.Printf("HTTP_REQUEST_FAILED: %v\n",err);os.Exit(43)}
  defer resp.Body.Close();body,_:=io.ReadAll(resp.Body)
  json.NewEncoder(os.Stdout).Encode(map[string]any{"listen":"loopback","sdk_http_status":resp.StatusCode,"body":string(body)})
  if resp.StatusCode<400 {os.Exit(44)} // malformed request must reach SDK rejection
 case "exec-probe":
  err:=exec.Command("/synthetic-nonexistent-command").Run()
  fmt.Printf("EXEC_RESULT: %v\n",err)
 default: panic("unknown mode")
 }
}
