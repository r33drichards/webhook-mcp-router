package main

import (
	"bytes"
	"context"
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
