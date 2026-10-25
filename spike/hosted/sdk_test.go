package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
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
	if len(tools) != 4 {
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
