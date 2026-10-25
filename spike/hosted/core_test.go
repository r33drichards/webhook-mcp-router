package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func testFixture(t *testing.T) *fixture {
	t.Helper()
	return &fixture{state: t.TempDir(), receipts: t.TempDir(), token: strings.Repeat("a", 32), receiptToken: strings.Repeat("b", 32), key: bytes.Repeat([]byte{3}, 32)}
}
func TestDurabilityAndPathValidation(t *testing.T) {
	f := testFixture(t)
	id := "sub_ci_0123456789abcdef"
	if f.create("../escape") == nil {
		t.Fatal("path accepted")
	}
	if err := f.create(id); err != nil {
		t.Fatal(err)
	}
	fresh := &fixture{state: f.state}
	ids, err := fresh.list()
	if err != nil || len(ids) != 1 || ids[0] != id {
		t.Fatal("fresh reader lost registration")
	}
	if err := fresh.remove(id); err != nil {
		t.Fatal(err)
	}
	ids, _ = f.list()
	if len(ids) != 0 {
		t.Fatal("delete failed")
	}
}
func TestActualNativeDeliveryAndReceipt(t *testing.T) {
	f := testFixture(t)
	sink := httptest.NewTLSServer(http.HandlerFunc(f.callbackHandler))
	defer sink.Close()
	f.callback = sink.URL
	f.client = sink.Client()
	id := "sub_ci_0123456789abcdef"
	nonce := strings.Repeat("a", 32)
	if err := f.create(id); err != nil {
		t.Fatal(err)
	}
	eid, err := f.emit(context.Background(), id, nonce)
	if err != nil {
		t.Fatal(err)
	}
	fresh := &fixture{receipts: f.receipts, receiptToken: f.receiptToken}
	req := httptest.NewRequest("GET", "https://fixture/receipts?event_id="+eid, nil)
	req.Header.Set("Authorization", "Bearer "+f.receiptToken)
	out := httptest.NewRecorder()
	fresh.receiptHandler(out, req)
	var got receipt
	if json.Unmarshal(out.Body.Bytes(), &got) != nil || !got.SignatureVerified || got.Nonce != nonce || got.SubscriptionID != id || got.EventID != eid {
		t.Fatal("invalid receipt")
	}
}
func TestSignatureBeforeParsingAndReplay(t *testing.T) {
	f := testFixture(t)
	eid := "evt_" + strings.Repeat("a", 32)
	sid := "sub_ci_0123456789abcdef"
	stamp := strconv.FormatInt(time.Now().Unix(), 10)
	body, _ := json.Marshal(envelope{EventID: eid, Name: "webhook.received", Data: map[string]string{"nonce": strings.Repeat("b", 32)}})
	send := func(payload []byte, sig, ts string) int {
		req := httptest.NewRequest("POST", "https://fixture/callback", bytes.NewReader(payload))
		req.Header.Set("webhook-id", eid)
		req.Header.Set("webhook-timestamp", ts)
		req.Header.Set("webhook-signature", sig)
		req.Header.Set("X-MCP-Subscription-Id", sid)
		out := httptest.NewRecorder()
		f.callbackHandler(out, req)
		return out.Code
	}
	if send([]byte("not json"), "invalid", stamp) != 401 {
		t.Fatal("parsed before auth")
	}
	old := strconv.FormatInt(time.Now().Unix()-600, 10)
	if send(body, signature(f.key, eid, old, body), old) != 401 {
		t.Fatal("stale accepted")
	}
	sig := signature(f.key, eid, stamp, body)
	if send(append(body, ' '), sig, stamp) != 401 {
		t.Fatal("tamper accepted")
	}
	if send(body, sig, stamp) != 204 {
		t.Fatal("valid rejected")
	}
	if send(body, sig, stamp) != 409 {
		t.Fatal("replay accepted")
	}
	if _, err := os.Stat(filepath.Join(f.receipts, eid)); err != nil {
		t.Fatal(err)
	}
}

func TestRegisteredPoliciesNativeOPAIsolation(t *testing.T) {
	f := testFixture(t)
	id := "sub_ci_0123456789abcdef"
	nonce := strings.Repeat("a", 32)
	if err := f.create(id); err != nil {
		t.Fatal(err)
	}
	good := `package router
import rego.v1
routes := [{"subscription_id":"` + id + `","data":{"nonce":input.nonce,"selected":"only-this"}}] if input.action == "opened"
else := []`
	if err := f.registerPolicy("policy_good", good); err != nil {
		t.Fatal(err)
	}
	if err := f.registerPolicy("policy_other", `package router
routes := [{"subscription_id":"https://example.invalid/callback","data":{"nonce":"`+nonce+`"}}]`); err != nil {
		t.Fatal(err)
	}
	// Corrupt one stored module to simulate an independently broken registration.
	if err := os.WriteFile(filepath.Join(f.state, "policies", "policy_bad.rego"), []byte("invalid rego"), 0600); err != nil {
		t.Fatal(err)
	}
	fresh := &fixture{state: f.state, token: f.token}
	out, err := fresh.routeVerified(context.Background(), map[string]any{"action": "opened", "nonce": nonce})
	if err != nil || len(out) != 3 {
		t.Fatalf("snapshot outcomes=%+v err=%v", out, err)
	}
	got := map[string]routingOutcome{}
	for _, item := range out {
		got[item.PolicyID] = item
	}
	if got["policy_bad"].Error == "" || got["policy_other"].Error == "" {
		t.Fatal("invalid policy/destination accepted")
	}
	match := got["policy_good"]
	if match.Error != "" || len(match.Routes) != 1 || match.Routes[0].SubscriptionID != id || match.Routes[0].Data["selected"] != "only-this" {
		t.Fatalf("good policy not isolated: %+v", match)
	}
	out, err = f.routeVerified(context.Background(), map[string]any{"action": "closed", "nonce": nonce})
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range out {
		if item.PolicyID == "policy_good" && (item.Error != "" || len(item.Routes) != 0) {
			t.Fatal("nonmatch routed")
		}
	}
}
func TestPolicyLimitsAndNoNetworkBuiltin(t *testing.T) {
	f := testFixture(t)
	if f.registerPolicy("../escape", "package router\nroutes := []") == nil {
		t.Fatal("path accepted")
	}
	if f.registerPolicy("policy_big", strings.Repeat("x", 32769)) == nil {
		t.Fatal("source limit absent")
	}
	if f.registerPolicy("policy_network", `package router
routes := http.send({"method":"GET","url":"https://example.invalid"})`) == nil {
		t.Fatal("network builtin accepted")
	}
	outcome := evaluateRegisteredPolicy(context.Background(), registeredPolicy{"policy_url", `package router
routes := [{"subscription_id":"sub_ci_0123456789abcdef","url":"https://example.invalid","data":{"nonce":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}]`}, map[string]any{}, map[string]bool{"sub_ci_0123456789abcdef": true})
	if outcome.Error == "" {
		t.Fatal("unknown URL decision field accepted")
	}
}
func TestIngressVerifiedOPAAndFixedSyntheticSink(t *testing.T) {
	f := testFixture(t)
	sink := httptest.NewTLSServer(http.HandlerFunc(f.callbackHandler))
	defer sink.Close()
	f.callback = sink.URL
	f.client = sink.Client()
	id := "sub_ci_0123456789abcdef"
	nonce := strings.Repeat("c", 32)
	if err := f.create(id); err != nil {
		t.Fatal(err)
	}
	if err := f.registerPolicy("policy_match", `package router
routes := [{"subscription_id":"`+id+`","data":{"nonce":input.nonce}}]`); err != nil {
		t.Fatal(err)
	}
	send := func(body []byte, sig string) *httptest.ResponseRecorder {
		req := httptest.NewRequest("POST", "https://fixture/hooks/github", bytes.NewReader(body))
		req.Header.Set("X-Hub-Signature-256", sig)
		w := httptest.NewRecorder()
		f.ingressHandler(w, req)
		return w
	}
	if w := send([]byte("bad-json"), "invalid"); w.Code != 401 {
		t.Fatal("parsed unauthenticated request")
	}
	body := []byte(`{"nonce":"` + nonce + `"}`)
	mac := hmac.New(sha256.New, f.key)
	mac.Write(body)
	w := send(body, "sha256="+hex.EncodeToString(mac.Sum(nil)))
	if w.Code != 200 {
		t.Fatalf("ingress status %d: %s", w.Code, w.Body.String())
	}
	var result struct {
		Policies []routingOutcome `json:"policies"`
	}
	if json.Unmarshal(w.Body.Bytes(), &result) != nil || len(result.Policies) != 1 || result.Policies[0].Error != "" || len(result.Policies[0].Routes) != 1 {
		t.Fatalf("route failed: %s", w.Body.String())
	}
	eid := result.Policies[0].Routes[0].EventID
	data, err := os.ReadFile(filepath.Join(f.receipts, eid))
	if err != nil {
		t.Fatal(err)
	}
	var got receipt
	if json.Unmarshal(data, &got) != nil || !got.SignatureVerified || got.Nonce != nonce || got.SubscriptionID != id {
		t.Fatal("independent sink receipt failed")
	}
}

func TestExpiredHostedWindowFailsClosed(t *testing.T) {
	t.Setenv("POC_EXPIRES_AT", "2000-01-01T00:00:00Z")
	if _, err := loadFixture(); err == nil || err.Error() != "POC_WINDOW_EXPIRED" {
		t.Fatal("expired hosted window accepted")
	}
}

func TestCredentialFreeStartupProbe(t *testing.T) {
	for _, name := range []string{"POC_TEST_TOKEN", "POC_RECEIPT_TOKEN", "POC_WEBHOOK_SECRET", "POC_STATE_DIR", "POC_RECEIPT_DIR", "POC_EXPIRES_AT"} {
		t.Setenv(name, "")
	}
	h := startupHandler()
	for _, tc := range []struct {
		method, path string
		status       int
		body         string
	}{
		{"GET", "/_poc/health", 200, `{"status":"runtime-ready"}`},
		{"POST", "/_poc/health", 405, ""},
		{"GET", "/mcp", 503, "POC_SIGNING_CONFIG_INVALID"},
		{"GET", "/receipts", 503, "POC_SIGNING_CONFIG_INVALID"},
		{"POST", "/hooks/github", 503, "POC_SIGNING_CONFIG_INVALID"},
	} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest(tc.method, tc.path, nil))
		if w.Code != tc.status || !strings.Contains(w.Body.String(), tc.body) {
			t.Fatalf("unexpected startup result for %s", tc.path)
		}
	}
}
