package main

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPolicyIsolationAndRegisteredIDs(t *testing.T) {
	r := &routeRegistry{}
	err := r.replace([]routePolicy{
		{"bad", `package router
routes := syntax error`},
		{"good", `package router
routes := [{"subscription_id":"sub_ok","data":{"selected":"value"}}]`},
		{"unknown", `package router
routes := [{"subscription_id":"https://example.invalid/","data":{}}]`},
	}, map[string]bool{"sub_ok": true})
	if err != nil {
		t.Fatal(err)
	}
	out := evaluateSnapshot(context.Background(), r, map[string]any{})
	if len(out) != 3 || out[0].Error == "" || out[1].Error != "" || len(out[1].Routes) != 1 || out[1].Routes[0].SubscriptionID != "sub_ok" || out[2].Error != "subscription_invalid" {
		t.Fatalf("unexpected outcomes: %+v", out)
	}
}
func TestSignatureBeforeJSON(t *testing.T) {
	req := httptest.NewRequest("POST", "http://localhost/hooks/synthetic-router", strings.NewReader("not-json"))
	w := httptest.NewRecorder()
	serveSyntheticRouter(w, req)
	if w.Code != 401 {
		t.Fatalf("want signature rejection before parse, got %d", w.Code)
	}
}
