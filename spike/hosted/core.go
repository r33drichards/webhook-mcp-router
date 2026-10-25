package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var idPattern = regexp.MustCompile(`^sub_ci_[a-f0-9]{16}$`)
var noncePattern = regexp.MustCompile(`^[a-f0-9]{32}$`)
var eventPattern = regexp.MustCompile(`^evt_[a-f0-9]{32}$`)
var invalid = errors.New("invalid synthetic request")

type fixture struct {
	state, receipts, token, receiptToken, callback string
	key                                            []byte
	client                                         *http.Client
}
type receipt struct {
	Received          bool   `json:"received"`
	SubscriptionID    string `json:"subscription_id"`
	EventID           string `json:"event_id"`
	Nonce             string `json:"nonce"`
	SignatureVerified bool   `json:"signature_verified"`
}
type envelope struct {
	EventID   string            `json:"eventId"`
	Name      string            `json:"name"`
	Timestamp string            `json:"timestamp"`
	Data      map[string]string `json:"data"`
	Cursor    any               `json:"cursor"`
}

func loadFixture() (*fixture, error) {
	f := &fixture{state: os.Getenv("POC_STATE_DIR"), receipts: os.Getenv("POC_RECEIPT_DIR"), token: os.Getenv("POC_TEST_TOKEN"), receiptToken: os.Getenv("POC_RECEIPT_TOKEN"), callback: os.Getenv("POC_CALLBACK_URL")}
	key, err := base64.StdEncoding.DecodeString(strings.TrimPrefix(os.Getenv("POC_WEBHOOK_SECRET"), "whsec_"))
	u, uerr := url.Parse(f.callback)
	if err != nil || !strings.HasPrefix(os.Getenv("POC_WEBHOOK_SECRET"), "whsec_") || len(key) < 24 || len(key) > 64 || len(f.token) < 32 || len(f.receiptToken) < 32 || !filepath.IsAbs(f.state) || !filepath.IsAbs(f.receipts) || f.state == f.receipts || uerr != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("missing reviewed fixture configuration")
	}
	f.key = key
	// Destination is a trusted operator-configured fixed sink, never RPC input.
	// No ambient proxies or redirects. Outbound WASI support remains unproven.
	f.client = &http.Client{Timeout: 10 * time.Second, Transport: &http.Transport{Proxy: nil}, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect refused") }}
	for _, d := range []string{f.state, f.receipts} {
		if err := os.MkdirAll(d, 0700); err != nil {
			return nil, errors.New("storage unavailable")
		}
	}
	return f, nil
}
func authorized(r *http.Request, token string) bool {
	return token != "" && subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+token)) == 1
}
func (f *fixture) create(id string) error {
	if !idPattern.MatchString(id) {
		return invalid
	}
	file, err := os.OpenFile(filepath.Join(f.state, id), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		if os.IsExist(err) {
			return nil
		}
		return errors.New("registration storage failed")
	}
	// Empty files are registration markers: no partially written JSON record.
	return file.Close()
}
func (f *fixture) list() ([]string, error) {
	entries, err := os.ReadDir(f.state)
	if err != nil {
		return nil, errors.New("registration read failed")
	}
	ids := []string{}
	for _, e := range entries {
		if !e.IsDir() && idPattern.MatchString(e.Name()) {
			ids = append(ids, e.Name())
		}
	}
	return ids, nil
}
func (f *fixture) remove(id string) error {
	if !idPattern.MatchString(id) {
		return invalid
	}
	err := os.Remove(filepath.Join(f.state, id))
	if os.IsNotExist(err) {
		return nil
	}
	return err
}
func signature(key []byte, id, stamp string, body []byte) string {
	h := hmac.New(sha256.New, key)
	h.Write([]byte(id + "." + stamp + "."))
	h.Write(body)
	return "v1," + base64.StdEncoding.EncodeToString(h.Sum(nil))
}
func (f *fixture) emit(ctx context.Context, id, nonce string) (string, error) {
	if !idPattern.MatchString(id) || !noncePattern.MatchString(nonce) {
		return "", invalid
	}
	if _, err := os.Stat(filepath.Join(f.state, id)); err != nil {
		return "", errors.New("subscription missing")
	}
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	eventID := "evt_" + hex.EncodeToString(random)
	body, _ := json.Marshal(envelope{EventID: eventID, Name: "webhook.received", Timestamp: time.Now().UTC().Format(time.RFC3339Nano), Data: map[string]string{"nonce": nonce}, Cursor: nil})
	stamp := strconv.FormatInt(time.Now().Unix(), 10)
	req, err := http.NewRequestWithContext(ctx, "POST", f.callback, bytes.NewReader(body))
	if err != nil {
		return "", invalid
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("webhook-id", eventID)
	req.Header.Set("webhook-timestamp", stamp)
	req.Header.Set("webhook-signature", signature(f.key, eventID, stamp, body))
	req.Header.Set("X-MCP-Subscription-Id", id)
	response, err := f.client.Do(req)
	if err != nil {
		return "", errors.New("callback transport failed")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		return "", errors.New("callback rejected")
	}
	return eventID, nil
}
func (f *fixture) callbackHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "method", 405)
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 4096))
	if err != nil {
		http.Error(w, "body", 400)
		return
	}
	id, stamp, sid := r.Header.Get("webhook-id"), r.Header.Get("webhook-timestamp"), r.Header.Get("X-MCP-Subscription-Id")
	seconds, err := strconv.ParseInt(stamp, 10, 64)
	now := time.Now().Unix()
	if err != nil || seconds < now-300 || seconds > now+30 || !eventPattern.MatchString(id) || !idPattern.MatchString(sid) || !hmac.Equal([]byte(r.Header.Get("webhook-signature")), []byte(signature(f.key, id, stamp, body))) {
		http.Error(w, "signature", 401)
		return
	}
	var event envelope
	if json.Unmarshal(body, &event) != nil || event.EventID != id || event.Name != "webhook.received" || !noncePattern.MatchString(event.Data["nonce"]) {
		http.Error(w, "event", 400)
		return
	}
	// Write-once receipt provides basic replay rejection, separate from registrations.
	out, err := os.OpenFile(filepath.Join(f.receipts, id), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		http.Error(w, "duplicate or storage failure", 409)
		return
	}
	err = json.NewEncoder(out).Encode(receipt{true, sid, id, event.Data["nonce"], true})
	closeErr := out.Close()
	if err != nil || closeErr != nil {
		http.Error(w, "storage", 500)
		return
	}
	w.WriteHeader(204)
}
func (f *fixture) receiptHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" || !authorized(r, f.receiptToken) {
		http.Error(w, "unauthorized", 401)
		return
	}
	id := r.URL.Query().Get("event_id")
	if !eventPattern.MatchString(id) {
		http.Error(w, "id", 400)
		return
	}
	body, err := os.ReadFile(filepath.Join(f.receipts, id))
	w.Header().Set("Content-Type", "application/json")
	if os.IsNotExist(err) {
		io.WriteString(w, `{"received":false}`)
		return
	}
	if err != nil {
		http.Error(w, "storage", 500)
		return
	}
	w.Write(body)
}
