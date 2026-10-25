package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestOfficialSDKStatelessRegistration(t *testing.T) {
	f := testFixture(t)
	call := func(method string, params any) map[string]any {
		t.Helper()
		body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
		req := httptest.NewRequest("POST", "http://localhost/mcp", bytes.NewReader(body))
		req.Header.Set("Authorization", "Bearer "+f.token)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json, text/event-stream")
		req.Header.Set("MCP-Protocol-Version", "2025-06-18")
		// Recreate the server for every invocation; only filesystem state persists.
		out := httptest.NewRecorder()
		handler(f).ServeHTTP(out, req)
		if out.Code != 200 || out.Header().Get("Mcp-Session-Id") != "" {
			t.Fatalf("HTTP/session assertion: %d", out.Code)
		}
		var result map[string]any
		if json.Unmarshal(out.Body.Bytes(), &result) != nil || result["error"] != nil {
			t.Fatal("RPC failed", method)
		}
		return result["result"].(map[string]any)
	}
	call("initialize", map[string]any{"protocolVersion": "2025-06-18", "capabilities": map[string]any{}, "clientInfo": map[string]any{"name": "test", "version": "1"}})
	tools := call("tools/list", map[string]any{})["tools"].([]any)
	if len(tools) != 6 {
		t.Fatal("tools missing")
	}
	result := call("tools/call", map[string]any{"name": "synthetic_subscription_create", "arguments": map[string]any{"id": "sub_ci_0123456789abcdef"}})
	if result["isError"] == true {
		t.Fatal("create failed")
	}
	listed := call("tools/call", map[string]any{"name": "synthetic_subscription_list", "arguments": map[string]any{}})
	ids := listed["structuredContent"].(map[string]any)["ids"].([]any)
	if len(ids) != 1 || ids[0] != "sub_ci_0123456789abcdef" {
		t.Fatal("readback failed")
	}
	out := httptest.NewRecorder()
	handler(f).ServeHTTP(out, httptest.NewRequest(http.MethodPost, "http://localhost/mcp", nil))
	if out.Code != 401 {
		t.Fatal("unauthenticated access")
	}
}

// Each RPC gets a fresh handler to exercise storage independent of SDK sessions.
func eventRPC(t *testing.T, f *fixture, version, method string, params map[string]any, wantError bool) map[string]any {
	t.Helper()
	if version == "2026-07-28" {
		params["_meta"] = map[string]any{"io.modelcontextprotocol/protocolVersion": version, "io.modelcontextprotocol/clientInfo": map[string]any{"name": "event-test", "version": "1"}, "io.modelcontextprotocol/clientCapabilities": map[string]any{}}
	}
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
	req := httptest.NewRequest("POST", "https://fixture/mcp", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("MCP-Protocol-Version", version)
	out := httptest.NewRecorder()
	handler(f).ServeHTTP(out, req)
	var response map[string]any
	if out.Code != 200 || json.Unmarshal(out.Body.Bytes(), &response) != nil {
		t.Fatalf("HTTP %d %s", out.Code, out.Body.String())
	}
	if wantError {
		if response["error"] == nil {
			t.Fatal("expected RPC error")
		}
		return response
	}
	if response["error"] != nil {
		t.Fatalf("RPC %s failed: %v", method, response["error"])
	}
	return response["result"].(map[string]any)
}
func eventArguments(f *fixture) map[string]any {
	return map[string]any{"name": eventName, "arguments": map[string]any{}, "delivery": map[string]any{"mode": "webhook", "url": f.callback, "secret": "whsec_" + base64.StdEncoding.EncodeToString(f.key)}}
}
func TestWeeChatEventWireLifecycle(t *testing.T) {
	f := testFixture(t)
	challenges := 0
	sink := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(body))
		var shape map[string]any
		json.Unmarshal(body, &shape)
		if shape["type"] == "verification" {
			challenges++
		}
		f.callbackHandler(w, r)
	}))
	defer sink.Close()
	f.callback = sink.URL
	f.client = sink.Client()
	discovery := eventRPC(t, f, "2026-07-28", "server/discover", map[string]any{}, false)
	if discovery["capabilities"].(map[string]any)["events"] == nil {
		t.Fatal("top-level events capability missing")
	}
	if discovery["supportedVersions"] == nil {
		t.Fatal("SDK discovery fields lost")
	}
	catalog := eventRPC(t, f, "2026-07-28", "events/list", map[string]any{}, false)
	if catalog["events"].([]any)[0].(map[string]any)["name"] != eventName {
		t.Fatal("catalog mismatch")
	}
	args := eventArguments(f)
	args["ttlMs"] = float64(10000)
	first := eventRPC(t, f, "2026-07-28", "events/subscribe", args, false)
	id := first["id"].(string)
	if first["cursor"] != id+":0" || first["truncated"] != false || first["refreshBefore"] == nil {
		t.Fatal("subscription result contract")
	}
	serialized, _ := json.Marshal(first)
	if bytes.Contains(serialized, []byte("whsec_")) {
		t.Fatal("secret exposed")
	}
	second := eventRPC(t, f, "2026-07-28", "events/subscribe", eventArguments(f), false)
	if second["id"] != id || challenges != 2 {
		t.Fatal("refresh identity or verification missing")
	}
	if _, err := loadEventSubscription(f, id, eventOwner(f.token)); err != nil {
		t.Fatal("persisted grant unreadable", err)
	}
	other := *f
	other.token = "other-owner-with-long-enough-test-token"
	if _, err := loadEventSubscription(&other, id, eventOwner(other.token)); err == nil {
		t.Fatal("cross-owner grant read")
	}
	unsubscribe := eventArguments(f)
	delete(unsubscribe["delivery"].(map[string]any), "secret")
	eventRPC(t, &other, "2026-07-28", "events/unsubscribe", unsubscribe, false)
	if _, err := loadEventSubscription(f, id, eventOwner(f.token)); err != nil {
		t.Fatal("cross-owner unsubscribe removed grant")
	}
	eventRPC(t, f, "2026-07-28", "events/unsubscribe", unsubscribe, false)
	eventRPC(t, f, "2026-07-28", "events/unsubscribe", unsubscribe, false)
	if _, err := loadEventSubscription(f, id, eventOwner(f.token)); err == nil {
		t.Fatal("grant survived unsubscribe")
	}
}
func TestEventVerificationAndTTLFailClosed(t *testing.T) {
	f := testFixture(t)
	sink := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, `{"challenge":"wrong"}`) }))
	defer sink.Close()
	f.callback = sink.URL
	f.client = sink.Client()
	args := eventArguments(f)
	eventRPC(t, f, "2026-07-28", "events/subscribe", args, true)
	if ids, _ := f.list(); len(ids) != 0 {
		t.Fatal("failed challenge activated subscription")
	}
	args["ttlMs"] = 0
	eventRPC(t, f, "2026-07-28", "events/subscribe", args, true)
	args = eventArguments(f)
	args["delivery"].(map[string]any)["url"] = "https://unregistered.invalid/callback"
	eventRPC(t, f, "2026-07-28", "events/subscribe", args, true)
	args = eventArguments(f)
	args["extra"] = "secret-must-not-leak"
	response := eventRPC(t, f, "2026-07-28", "events/subscribe", args, true)
	body, _ := json.Marshal(response)
	if bytes.Contains(body, []byte("secret-must-not-leak")) {
		t.Fatal("validation echoed request")
	}
	id := "sub_" + strings.Repeat("a", 64)
	if err := saveEventSubscription(f, &eventSubscription{ID: id, Owner: eventOwner(f.token), URL: f.callback, Key: f.key, Expires: time.Now().Add(-time.Second)}); err != nil {
		t.Fatal(err)
	}
	if _, err := loadEventSubscription(f, id, eventOwner(f.token)); err == nil {
		t.Fatal("expired grant accepted")
	}
}
