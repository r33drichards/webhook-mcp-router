package main

// Synthetic-only experiment: it cannot deliver externally or load production keys.
import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	"github.com/open-policy-agent/opa/v1/ast"
	"github.com/open-policy-agent/opa/v1/rego"
)

const syntheticKey = "public-synthetic-test-key-not-for-production"
const maxRouterBody = 65536

type routePolicy struct{ ID, Rego string }
type routeRecord struct {
	SubscriptionID string `json:"subscription_id"`
	Data           any    `json:"data"`
}
type policyOutcome struct {
	Policy string        `json:"policy"`
	Routes []routeRecord `json:"routes"`
	Error  string        `json:"error,omitempty"`
}
type routeRegistry struct {
	sync.RWMutex
	policies      []routePolicy
	subscriptions map[string]bool
}

var syntheticRegistry = routeRegistry{
	policies: []routePolicy{{"opened", `package router
import rego.v1
routes := [{"subscription_id":"sub_demo","data":{"action":input.action}}] if input.action == "opened"
else := []`}}, subscriptions: map[string]bool{"sub_demo": true},
}

// replace snapshots configuration. No network management endpoint is exposed.
func (r *routeRegistry) replace(policies []routePolicy, subscriptions map[string]bool) error {
	if len(policies) > 16 || len(subscriptions) > 100 {
		return fmt.Errorf("registry_limit")
	}
	ps := append([]routePolicy(nil), policies...)
	for _, p := range ps {
		if len(p.Rego) > 32768 || len(p.ID) > 64 {
			return fmt.Errorf("policy_limit")
		}
	}
	subs := map[string]bool{}
	for id, active := range subscriptions {
		subs[id] = active
	}
	r.Lock()
	defer r.Unlock()
	r.policies = ps
	r.subscriptions = subs
	return nil
}
func (r *routeRegistry) snapshot() ([]routePolicy, map[string]bool) {
	r.RLock()
	defer r.RUnlock()
	ps := append([]routePolicy(nil), r.policies...)
	subs := map[string]bool{}
	for id, active := range r.subscriptions {
		subs[id] = active
	}
	return ps, subs
}
func pureCapabilities() *ast.Capabilities {
	c := ast.CapabilitiesForThisVersion()
	allowed := map[string]bool{"eq": true, "neq": true, "equal": true, "assign": true, "count": true, "concat": true, "contains": true, "startswith": true, "endswith": true, "lower": true, "upper": true, "object.get": true, "is_string": true, "is_array": true, "is_object": true, "is_number": true, "sort": true}
	bs := c.Builtins[:0]
	for _, b := range c.Builtins {
		if allowed[b.Name] {
			bs = append(bs, b)
		}
	}
	c.Builtins = bs
	c.AllowNet = []string{}
	return c
}
func evaluatePolicy(ctx context.Context, p routePolicy, input any, subs map[string]bool) (out policyOutcome) {
	out.Policy = p.ID
	out.Routes = []routeRecord{}
	// An evaluator panic must not prevent the following policy from being evaluated.
	defer func() {
		if recover() != nil {
			out.Routes = []routeRecord{}
			out.Error = "policy_failed"
		}
	}()
	bounded, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
	defer cancel()
	rs, err := rego.New(rego.Query("data.router.routes"), rego.Module("route.rego", p.Rego), rego.Capabilities(pureCapabilities()), rego.Input(input)).Eval(bounded)
	if err != nil || len(rs) != 1 || len(rs[0].Expressions) != 1 {
		out.Error = "policy_failed"
		return
	}
	b, err := json.Marshal(rs[0].Expressions[0].Value)
	if err != nil || len(b) > 16384 {
		out.Error = "decision_limit"
		return
	}
	var routes []routeRecord
	if json.Unmarshal(b, &routes) != nil || len(routes) > 100 {
		out.Error = "decision_invalid"
		return
	}
	seen := map[string]bool{}
	for _, route := range routes {
		if !subs[route.SubscriptionID] || seen[route.SubscriptionID] {
			out.Error = "subscription_invalid"
			return
		}
		seen[route.SubscriptionID] = true
	}
	out.Routes = routes
	return
}
func evaluateSnapshot(ctx context.Context, r registrationReader, input any) []policyOutcome {
	ps, subs := r.snapshot()
	out := make([]policyOutcome, 0, len(ps))
	for _, p := range ps {
		out = append(out, evaluatePolicy(ctx, p, input, subs))
	}
	return out
}
func serveSyntheticRouter(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "method_invalid", 405)
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxRouterBody+1))
	if err != nil || len(raw) > maxRouterBody {
		http.Error(w, "body_limit", 413)
		return
	}
	mac := hmac.New(sha256.New, []byte(syntheticKey))
	mac.Write(raw)
	expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(r.Header.Get("X-Hub-Signature-256"))) {
		http.Error(w, "signature_invalid", 401)
		return
	}
	var input map[string]any
	if json.Unmarshal(raw, &input) != nil || input == nil {
		http.Error(w, "json_invalid", 400)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	results := evaluateSnapshot(ctx, &syntheticRegistry, input)
	// The only sink is the response to the local synthetic caller; no HTTP sender exists.
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"mode": "synthetic-dry-run", "policies": results})
}
