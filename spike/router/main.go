// Synthetic feasibility probe, not a webhook listener or production router.
package main

import (
 "context"
 "encoding/json"
 "fmt"
 "io"
 "os"
 "time"
 "github.com/open-policy-agent/opa/v1/rego"
)
const policy = `package router
import rego.v1
subscription_ids := [s.id |
 some s in input.subscriptions
 input.event.type == "pull_request"
 input.event.action == "opened"
 input.event.repository == s.repository
]`
func main() {
 if err := run(); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
func run() error {
 raw, err := io.ReadAll(io.LimitReader(os.Stdin, 65537)); if err != nil { return err }
 if len(raw)>65536 { return fmt.Errorf("input too large") }
 var input any
 if err=json.Unmarshal(raw,&input); err!=nil { return err }
 ctx,cancel:=context.WithTimeout(context.Background(),2*time.Second); defer cancel()
 rs,err:=rego.New(rego.Query("data.router.subscription_ids"),rego.Module("routes.rego",policy),rego.Input(input)).Eval(ctx)
 if err!=nil { return err }
 if len(rs)!=1 || len(rs[0].Expressions)!=1 { return fmt.Errorf("unexpected decision") }
 return json.NewEncoder(os.Stdout).Encode(rs[0].Expressions[0].Value)
}
