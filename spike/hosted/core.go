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
	"sync"

	"github.com/open-policy-agent/opa/v1/ast"
	"github.com/open-policy-agent/opa/v1/rego"
	"time"
)

var idPattern = regexp.MustCompile(`^(sub_ci_[a-f0-9]{16}|sub_[a-f0-9]{64})$`)
var noncePattern = regexp.MustCompile(`^[a-f0-9]{32}$`)
var eventPattern = regexp.MustCompile(`^evt_[a-f0-9]{32}$`)
var invalid = errors.New("invalid synthetic request")

type fixture struct {
	state, receipts, token, receiptToken, callback string
	key                                            []byte
	client                                         *http.Client
	policyMu                                       sync.RWMutex
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
	if raw := os.Getenv("POC_EXPIRES_AT"); raw != "" {
		expiry, err := time.Parse(time.RFC3339, raw)
		if err != nil || !time.Now().Before(expiry) {
			return nil, errors.New("synthetic test window expired")
		}
	}
	f := &fixture{state: os.Getenv("POC_STATE_DIR"), receipts: os.Getenv("POC_RECEIPT_DIR"), token: os.Getenv("POC_TEST_TOKEN"), receiptToken: os.Getenv("POC_RECEIPT_TOKEN"), callback: os.Getenv("POC_CALLBACK_URL")}
	key, err := base64.StdEncoding.DecodeString(strings.TrimPrefix(os.Getenv("POC_WEBHOOK_SECRET"), "whsec_"))
	u, uerr := url.Parse(f.callback)
	if err != nil || !strings.HasPrefix(os.Getenv("POC_WEBHOOK_SECRET"), "whsec_") || len(key) < 24 || len(key) > 64 || len(f.token) < 32 || len(f.receiptToken) < 32 || !filepath.IsAbs(f.state) || !filepath.IsAbs(f.receipts) || f.state == f.receipts || uerr != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("missing reviewed fixture configuration")
	}
	f.key = key
	// Destination is a trusted operator-configured fixed sink, never RPC input.
	// No ambient proxies or redirects; verified WASIX nonblocking transport.
	f.client, err = newHTTPClient()
	if err != nil {
		return nil, err
	}
	for _, d := range []string{f.state, f.receipts, filepath.Join(f.state, "policies")} {
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
	return f.emitData(ctx, id, map[string]string{"nonce": nonce})
}
func (f *fixture) emitData(ctx context.Context, id string, data map[string]string) (string, error) {
	if !idPattern.MatchString(id) || !noncePattern.MatchString(data["nonce"]) {
		return "", invalid
	}
	record, err := os.ReadFile(filepath.Join(f.state, id))
	if err != nil {
		return "", errors.New("subscription missing")
	}
	key := f.key
	// Empty markers are the explicitly separate legacy synthetic fixture path.
	// Protocol-created JSON grants must pass owner/expiry validation every send.
	if len(record) > 0 {
		grant, err := loadEventSubscription(f, id, eventOwner(f.token))
		if err != nil {
			return "", errors.New("subscription inactive")
		}
		key = grant.Key
	}
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	eventID := "evt_" + hex.EncodeToString(random)
	body, _ := json.Marshal(envelope{EventID: eventID, Name: "webhook.received", Timestamp: time.Now().UTC().Format(time.RFC3339Nano), Data: data, Cursor: nil})
	stamp := strconv.FormatInt(time.Now().Unix(), 10)
	req, err := http.NewRequestWithContext(ctx, "POST", f.callback, bytes.NewReader(body))
	if err != nil {
		return "", invalid
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("webhook-id", eventID)
	req.Header.Set("webhook-timestamp", stamp)
	req.Header.Set("webhook-signature", signature(key, eventID, stamp, body))
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
	if err != nil || seconds < now-300 || seconds > now+30 || !(eventPattern.MatchString(id) || verificationPattern.MatchString(id)) || !idPattern.MatchString(sid) || !hmac.Equal([]byte(r.Header.Get("webhook-signature")), []byte(signature(f.key, id, stamp, body))) {
		http.Error(w, "signature", 401)
		return
	}
	if verificationPattern.MatchString(id) {
		var challenge struct {
			Type      string `json:"type"`
			Challenge string `json:"challenge"`
		}
		if json.Unmarshal(body, &challenge) != nil || challenge.Type != "verification" || len(challenge.Challenge) < 16 || len(challenge.Challenge) > 256 {
			http.Error(w, "challenge", 400)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"challenge": challenge.Challenge})
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

var verificationPattern = regexp.MustCompile(`^verify_[a-f0-9]{32}$`)
var policyPattern = regexp.MustCompile(`^policy_[a-z0-9_-]{1,48}$`)

type registeredPolicy struct {
	ID     string `json:"id"`
	Source string `json:"source"`
}
type selectedRoute struct {
	SubscriptionID string            `json:"subscription_id"`
	Data           map[string]string `json:"data"`
	EventID        string            `json:"event_id,omitempty"`
}
type routingOutcome struct {
	PolicyID string          `json:"policy_id"`
	Routes   []selectedRoute `json:"routes"`
	Error    string          `json:"error,omitempty"`
}

func policyCapabilities() *ast.Capabilities {
	c := ast.CapabilitiesForThisVersion()
	allowed := map[string]bool{"eq": true, "neq": true, "equal": true, "assign": true, "gt": true, "gte": true, "lt": true, "lte": true, "count": true, "concat": true, "contains": true, "startswith": true, "endswith": true, "lower": true, "upper": true, "object.get": true, "is_string": true, "is_array": true, "is_object": true, "is_number": true, "sort": true}
	builtins := make([]*ast.Builtin, 0, len(c.Builtins))
	for _, b := range c.Builtins {
		if allowed[b.Name] {
			builtins = append(builtins, b)
		}
	}
	c.Builtins = builtins
	c.AllowNet = []string{}
	return c
}
func (f *fixture) registerPolicy(id, source string) error {
	if !policyPattern.MatchString(id) || len(source) == 0 || len(source) > 32768 {
		return errors.New("policy invalid")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	_, err := rego.New(rego.Query("data.router.routes"), rego.Module("policy.rego", source), rego.Capabilities(policyCapabilities())).PrepareForEval(ctx)
	if err != nil {
		return errors.New("policy validation failed")
	}
	f.policyMu.Lock()
	defer f.policyMu.Unlock()
	dir := filepath.Join(f.state, "policies")
	if err := os.MkdirAll(dir, 0700); err != nil {
		return errors.New("policy storage failed")
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return errors.New("policy storage failed")
	}
	if len(entries) >= 16 {
		if _, err := os.Stat(filepath.Join(dir, id+".rego")); err != nil {
			return errors.New("policy limit")
		}
	}
	file, err := os.CreateTemp(dir, ".policy-")
	if err != nil {
		return errors.New("policy storage failed")
	}
	name := file.Name()
	defer os.Remove(name)
	if _, err = file.WriteString(source); err != nil {
		file.Close()
		return errors.New("policy storage failed")
	}
	if file.Close() != nil || os.Rename(name, filepath.Join(dir, id+".rego")) != nil {
		return errors.New("policy storage failed")
	}
	return nil
}
func (f *fixture) listPolicies() ([]registeredPolicy, error) {
	f.policyMu.RLock()
	defer f.policyMu.RUnlock()
	return f.readPolicies()
}
func (f *fixture) readPolicies() ([]registeredPolicy, error) {
	entries, err := os.ReadDir(filepath.Join(f.state, "policies"))
	if os.IsNotExist(err) {
		return []registeredPolicy{}, nil
	}
	if err != nil {
		return nil, errors.New("policy read failed")
	}
	policies := []registeredPolicy{}
	for _, entry := range entries {
		id := strings.TrimSuffix(entry.Name(), ".rego")
		if entry.IsDir() || entry.Name() != id+".rego" || !policyPattern.MatchString(id) {
			continue
		}
		if len(policies) >= 16 {
			return nil, errors.New("policy limit")
		}
		file, err := os.Open(filepath.Join(f.state, "policies", entry.Name()))
		if err != nil {
			return nil, errors.New("policy read failed")
		}
		body, err := io.ReadAll(io.LimitReader(file, 32769))
		file.Close()
		if err != nil || len(body) > 32768 {
			return nil, errors.New("policy limit")
		}
		policies = append(policies, registeredPolicy{id, string(body)})
	}
	return policies, nil
}
func evaluateRegisteredPolicy(ctx context.Context, p registeredPolicy, input any, eligible map[string]bool) (out routingOutcome) {
	out = routingOutcome{PolicyID: p.ID, Routes: []selectedRoute{}}
	defer func() {
		if recover() != nil {
			out.Error = "policy_failed"
			out.Routes = []selectedRoute{}
		}
	}()
	bounded, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
	defer cancel()
	rs, err := rego.New(rego.Query("data.router.routes"), rego.Module("policy.rego", p.Source), rego.Capabilities(policyCapabilities()), rego.Input(input)).Eval(bounded)
	if err != nil || len(rs) != 1 || len(rs[0].Expressions) != 1 {
		out.Error = "policy_failed"
		return
	}
	encoded, err := json.Marshal(rs[0].Expressions[0].Value)
	if err != nil || len(encoded) > 16384 {
		out.Error = "decision_limit"
		return
	}
	// Policies may select only IDs and string-valued data, never URLs or headers.
	var decisions []struct {
		SubscriptionID string            `json:"subscription_id"`
		Data           map[string]string `json:"data"`
	}
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&decisions) != nil || decisions == nil || len(decisions) > 16 {
		out.Error = "decision_invalid"
		return
	}
	routes := []selectedRoute{}
	seen := map[string]bool{}
	for _, decision := range decisions {
		if !eligible[decision.SubscriptionID] || seen[decision.SubscriptionID] || !noncePattern.MatchString(decision.Data["nonce"]) {
			out.Error = "subscription_or_data_invalid"
			return
		}
		seen[decision.SubscriptionID] = true
		routes = append(routes, selectedRoute{SubscriptionID: decision.SubscriptionID, Data: decision.Data})
	}
	out.Routes = routes
	return
}
func (f *fixture) routeVerified(ctx context.Context, input any) ([]routingOutcome, error) {
	// Snapshot once. Receiver path only reads registration/policy storage.
	f.policyMu.RLock()
	policies, err := f.readPolicies()
	ids, idErr := f.list()
	f.policyMu.RUnlock()
	if err != nil || idErr != nil {
		return nil, errors.New("routing snapshot failed")
	}
	eligible := map[string]bool{}
	for _, id := range ids {
		record, readErr := os.ReadFile(filepath.Join(f.state, id))
		if readErr != nil {
			continue
		}
		if len(record) > 0 {
			if _, err := loadEventSubscription(f, id, eventOwner(f.token)); err != nil {
				continue
			}
		}
		eligible[id] = true
	}
	outcomes := make([]routingOutcome, 0, len(policies))
	for _, p := range policies {
		outcomes = append(outcomes, evaluateRegisteredPolicy(ctx, p, input, eligible))
	}
	return outcomes, nil
}
func (f *fixture) ingressHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "method", 405)
		return
	}
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 65536))
	if err != nil {
		http.Error(w, "body", 413)
		return
	}
	// Separate signing convention from outbound Standard Webhooks. This fixture
	// uses its configured synthetic key for GitHub HMAC; production keys must split.
	mac := hmac.New(sha256.New, f.key)
	mac.Write(raw)
	if !hmac.Equal([]byte(r.Header.Get("X-Hub-Signature-256")), []byte("sha256="+hex.EncodeToString(mac.Sum(nil)))) {
		http.Error(w, "signature", 401)
		return
	}
	var input map[string]any
	if json.Unmarshal(raw, &input) != nil || input == nil {
		http.Error(w, "json", 400)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	outcomes, err := f.routeVerified(ctx, input)
	if err != nil {
		http.Error(w, "routing", 500)
		return
	}
	for i := range outcomes {
		if outcomes[i].Error != "" {
			continue
		}
		for j := range outcomes[i].Routes {
			route := &outcomes[i].Routes[j]
			eid, err := f.emitData(ctx, route.SubscriptionID, route.Data)
			if err != nil {
				outcomes[i].Error = "delivery_failed"
				continue
			}
			route.EventID = eid
		}
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"policies": outcomes, "mode": "controlled-synthetic-fixture"})
}
