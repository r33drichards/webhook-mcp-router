package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/modelcontextprotocol/go-sdk/mcp"
	"io"
	"net/http"
	"net/http/cgi"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

type idInput struct {
	ID string `json:"id"`
}
type emitInput struct {
	SubscriptionID string `json:"subscription_id"`
	Nonce          string `json:"nonce"`
}
type policyInput struct {
	ID     string `json:"id"`
	Source string `json:"source"`
}
type emptyInput struct{}
type output map[string]any

func handler(f *fixture) http.Handler {
	server := mcp.NewServer(&mcp.Implementation{Name: "synthetic-wcgi-events-poc", Version: "0.0.1"}, nil)
	installEvents(server, f)
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_subscription_create", Description: "Register synthetic ID for fixed test sink only"}, func(ctx context.Context, r *mcp.CallToolRequest, in idInput) (*mcp.CallToolResult, output, error) {
		err := f.create(in.ID)
		return nil, output{"id": in.ID, "status": "active"}, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_subscription_list", Description: "Read synthetic registrations from configured storage"}, func(ctx context.Context, r *mcp.CallToolRequest, in emptyInput) (*mcp.CallToolResult, output, error) {
		ids, err := f.list()
		return nil, output{"ids": ids}, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_subscription_delete", Description: "Remove a synthetic registration"}, func(ctx context.Context, r *mcp.CallToolRequest, in idInput) (*mcp.CallToolResult, output, error) {
		err := f.remove(in.ID)
		return nil, output{"id": in.ID}, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_emit", Description: "Send a synthetic nonce to the fixed controlled sink"}, func(ctx context.Context, r *mcp.CallToolRequest, in emitInput) (*mcp.CallToolResult, output, error) {
		id, err := f.emit(ctx, in.SubscriptionID, in.Nonce)
		return nil, output{"event_id": id}, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_policy_register", Description: "Validate and register a bounded routing Rego policy for the controlled sink"}, func(ctx context.Context, r *mcp.CallToolRequest, in policyInput) (*mcp.CallToolResult, output, error) {
		err := f.registerPolicy(in.ID, in.Source)
		return nil, output{"id": in.ID}, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_policy_list", Description: "List registered routing policies"}, func(ctx context.Context, r *mcp.CallToolRequest, in emptyInput) (*mcp.CallToolResult, output, error) {
		policies, err := f.listPolicies()
		return nil, output{"policies": policies}, err
	})
	sdk := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return server }, &mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	mux := http.NewServeMux()
	mux.HandleFunc("/mcp", func(w http.ResponseWriter, r *http.Request) {
		if !authorized(r, f.token) || r.Header.Get("Origin") != "" {
			http.Error(w, "unauthorized", 401)
			return
		}
		if r.Method != "POST" {
			http.Error(w, "method", 405)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 65536)
		sdk.ServeHTTP(w, r)
	})
	mux.HandleFunc("/hooks/github", f.ingressHandler)
	mux.HandleFunc("/callback", f.callbackHandler)
	mux.HandleFunc("/receipts", f.receiptHandler)
	return mux
}

// startupError contains only a fixed developer-defined code, never config values.
type startupError string

func (e startupError) Error() string { return string(e) }
func startupHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// This is the only credential-free path. No config, files, OPA or MCP
		// handlers are accessed; it proves the packaged CGI runtime can reply.
		if r.URL.Path == "/_poc/health" {
			w.Header().Set("Cache-Control", "no-store")
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = io.WriteString(w, `{"status":"runtime-ready"}`)
			return
		}
		f, err := loadFixture()
		if err != nil {
			code := "POC_STARTUP_FAILED"
			var known startupError
			if errors.As(err, &known) {
				code = string(known)
			}
			fmt.Fprintln(os.Stderr, code)
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Cache-Control", "no-store")
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(map[string]string{"error": code})
			return
		}
		handler(f).ServeHTTP(w, r)
	})
}
func main() {
	if err := cgi.Serve(startupHandler()); err != nil {
		fmt.Fprintln(os.Stderr, "POC_CGI_SERVE_FAILED")
		os.Exit(1)
	}
}

// Events follow the inspected WeeChat webhook convention. This POC restricts
// callback registration to the operator-configured controlled sink.
const eventName = "webhook.received"

var eventMu sync.Mutex // process-local only; this is not a multiwriter lease.

type eventDelivery struct {
	Mode   string `json:"mode"`
	URL    string `json:"url"`
	Secret string `json:"secret,omitempty"`
}
type eventParams struct {
	invalid bool
	mcp.ParamsBase
	Name      string         `json:"name"`
	Arguments map[string]any `json:"arguments"`
	Delivery  eventDelivery  `json:"delivery"`
	Cursor    *string        `json:"cursor,omitempty"`
	TTL       *int64         `json:"ttlMs,omitempty"`
}

func (p *eventParams) UnmarshalJSON(body []byte) error {
	type plain eventParams
	var value plain
	d := json.NewDecoder(bytes.NewReader(body))
	d.DisallowUnknownFields()
	if d.Decode(&value) != nil {
		*p = eventParams{invalid: true}
		return nil // Validate in handler: SDK decode errors echo raw params, including secrets.
	}
	*p = eventParams(value)
	return nil
}

type eventListParams struct {
	mcp.ParamsBase
	Cursor *string `json:"cursor,omitempty"`
}
type eventListResult struct {
	mcp.ResultBase
	Events []map[string]any `json:"events"`
}
type eventSubscribeResult struct {
	mcp.ResultBase
	ID            string `json:"id"`
	RefreshBefore string `json:"refreshBefore"`
	Cursor        any    `json:"cursor"`
	Truncated     bool   `json:"truncated"`
}
type eventEmptyResult struct{ mcp.ResultBase }
type eventSubscription struct {
	ID             string    `json:"id"`
	Owner          string    `json:"owner"`
	URL            string    `json:"url"`
	Key            []byte    `json:"-"`
	KeyFingerprint string    `json:"key_fingerprint"`
	Expires        time.Time `json:"expires"`
}

func eventOwner(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
func eventIdentity(owner string, p *eventParams) (string, error) {
	if p.invalid || owner == "" || p.Name != eventName || p.Arguments == nil || len(p.Arguments) != 0 || p.Delivery.Mode != "webhook" || p.Delivery.URL == "" {
		return "", errors.New("invalid event identity")
	}
	value, _ := json.Marshal([]any{owner, p.Delivery.URL, p.Name, p.Arguments})
	sum := sha256.Sum256(value)
	return "sub_" + hex.EncodeToString(sum[:]), nil
}
func loadEventSubscription(f *fixture, id, owner string) (*eventSubscription, error) {
	if !idPattern.MatchString(id) {
		return nil, errors.New("subscription invalid")
	}
	body, err := os.ReadFile(filepath.Join(f.state, id))
	if err != nil || len(body) > 4096 {
		return nil, errors.New("subscription unavailable")
	}
	var r eventSubscription
	if json.Unmarshal(body, &r) != nil || r.ID != id || r.Owner != owner || r.URL != f.callback || len(f.key) < 24 || len(f.key) > 64 || r.KeyFingerprint != eventKeyFingerprint(f.key) || !time.Now().Before(r.Expires) {
		return nil, errors.New("subscription unavailable")
	}
	r.Key = append([]byte(nil), f.key...)
	return &r, nil
}
func eventKeyFingerprint(key []byte) string {
	sum := sha256.Sum256(key)
	return hex.EncodeToString(sum[:])
}
func saveEventSubscription(f *fixture, r *eventSubscription) error {
	// The fixed sink key stays in runtime secret configuration, never the volume.
	if len(r.Key) < 24 || len(r.Key) > 64 || !hmac.Equal(r.Key, f.key) {
		return errors.New("subscription key invalid")
	}
	r.KeyFingerprint = eventKeyFingerprint(r.Key)
	file, err := os.CreateTemp(f.state, ".event-")
	if err != nil {
		return errors.New("subscription storage failed")
	}
	defer os.Remove(file.Name())
	if err = json.NewEncoder(file).Encode(r); err != nil {
		file.Close()
		return errors.New("subscription storage failed")
	}
	if err = file.Close(); err == nil {
		err = os.Rename(file.Name(), filepath.Join(f.state, r.ID))
	}
	if err != nil {
		return errors.New("subscription storage failed")
	}
	return nil
}
func verifyEventCallback(ctx context.Context, f *fixture, id string, key []byte) error {
	if f.client == nil {
		return errors.New("callback unavailable")
	}
	random := make([]byte, 32)
	if _, err := rand.Read(random); err != nil {
		return errors.New("challenge unavailable")
	}
	challenge := base64.RawURLEncoding.EncodeToString(random)
	body, _ := json.Marshal(map[string]string{"type": "verification", "challenge": challenge})
	eid := "verify_" + hex.EncodeToString(random[:16])
	stamp := strconv.FormatInt(time.Now().Unix(), 10)
	bounded, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(bounded, "POST", f.callback, bytes.NewReader(body))
	if err != nil {
		return errors.New("callback rejected")
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("webhook-id", eid)
	req.Header.Set("webhook-timestamp", stamp)
	req.Header.Set("webhook-signature", signature(key, eid, stamp, body))
	req.Header.Set("X-MCP-Subscription-Id", id)
	resp, err := f.client.Do(req)
	if err != nil {
		return errors.New("callback verification failed")
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 4097))
	var reply struct {
		Challenge string `json:"challenge"`
	}
	if err != nil || len(data) > 4096 || resp.StatusCode < 200 || resp.StatusCode >= 300 || json.Unmarshal(data, &reply) != nil || !hmac.Equal([]byte(reply.Challenge), []byte(challenge)) {
		return errors.New("callback verification failed")
	}
	return nil
}
func subscribeEvent(ctx context.Context, f *fixture, p *eventParams) (*eventSubscribeResult, error) {
	owner := eventOwner(f.token)
	id, err := eventIdentity(owner, p)
	if err != nil {
		return nil, err
	}
	if p.Delivery.URL != f.callback {
		return nil, errors.New("callback outside controlled sink")
	}
	if !strings.HasPrefix(p.Delivery.Secret, "whsec_") {
		return nil, errors.New("invalid callback secret")
	}
	encoded := strings.TrimPrefix(p.Delivery.Secret, "whsec_")
	key, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(key) < 24 || len(key) > 64 || base64.StdEncoding.EncodeToString(key) != encoded || !hmac.Equal(key, f.key) {
		return nil, errors.New("invalid callback secret")
	}
	ttl := int64(3600000)
	if p.TTL != nil {
		ttl = *p.TTL
	}
	if ttl <= 0 {
		return nil, errors.New("invalid ttlMs")
	}
	if ttl > 86400000 {
		ttl = 86400000
	}
	if p.Cursor != nil && *p.Cursor != id+":0" {
		return nil, errors.New("cursor replay unavailable")
	}
	eventMu.Lock()
	defer eventMu.Unlock()
	if err := verifyEventCallback(ctx, f, id, key); err != nil {
		return nil, err
	}
	expires := time.Now().Add(time.Duration(ttl) * time.Millisecond)
	if err := saveEventSubscription(f, &eventSubscription{ID: id, Owner: owner, URL: f.callback, Key: key, Expires: expires}); err != nil {
		return nil, err
	}
	return &eventSubscribeResult{ID: id, RefreshBefore: expires.UTC().Format(time.RFC3339Nano), Cursor: id + ":0", Truncated: false}, nil
}

// Wrap only discovery's serialized result, preserving all SDK fields. Supported
// ResultBase + middleware avoid a dependency patch for the top-level events key.
type eventDiscoveryResult struct {
	mcp.ResultBase
	value mcp.Result
}

func (r *eventDiscoveryResult) MarshalJSON() ([]byte, error) {
	// The SDK annotates known concrete results after middleware. Preserve the
	// required completion marker when wrapping a 2026 discovery result.
	if discover, ok := r.value.(*mcp.DiscoverResult); ok {
		discover.ResultType = "complete"
	}
	body, err := json.Marshal(r.value)
	if err != nil {
		return nil, err
	}
	var value map[string]any
	if err = json.Unmarshal(body, &value); err != nil {
		return nil, err
	}
	caps, ok := value["capabilities"].(map[string]any)
	if !ok {
		caps = map[string]any{}
		value["capabilities"] = caps
	}
	caps["events"] = map[string]any{}
	if meta := r.GetMeta(); len(meta) > 0 {
		previous, _ := value["_meta"].(map[string]any)
		if previous == nil {
			previous = map[string]any{}
		}
		for k, v := range meta {
			previous[k] = v
		}
		value["_meta"] = previous
	}
	return json.Marshal(value)
}
func installEvents(server *mcp.Server, f *fixture) {
	server.AddReceivingMiddleware(func(next mcp.MethodHandler) mcp.MethodHandler {
		return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
			result, err := next(ctx, method, req)
			if err == nil && (method == "server/discover" || method == "initialize") {
				return &eventDiscoveryResult{value: result}, nil
			}
			return result, err
		}
	})
	if err := mcp.AddReceivingCustomMethod(server, "events/list", func(ctx context.Context, ss *mcp.ServerSession, p *eventListParams) (*eventListResult, error) {
		if p.Cursor != nil {
			return nil, errors.New("invalid catalog cursor")
		}
		return &eventListResult{Events: []map[string]any{{"name": eventName, "description": "Synthetic controlled webhook event; subscribe explicitly.", "delivery": []string{"webhook"}, "inputSchema": map[string]any{"type": "object", "properties": map[string]any{}, "additionalProperties": false}, "payloadSchema": map[string]any{"type": "object", "properties": map[string]any{"nonce": map[string]any{"type": "string"}}, "required": []string{"nonce"}, "additionalProperties": false}}}}, nil
	}); err != nil {
		panic("event registration failed")
	}
	if err := mcp.AddReceivingCustomMethod(server, "events/subscribe", func(ctx context.Context, ss *mcp.ServerSession, p *eventParams) (*eventSubscribeResult, error) {
		return subscribeEvent(ctx, f, p)
	}); err != nil {
		panic("event registration failed")
	}
	if err := mcp.AddReceivingCustomMethod(server, "events/unsubscribe", func(ctx context.Context, ss *mcp.ServerSession, p *eventParams) (*eventEmptyResult, error) {
		if p.Delivery.Secret != "" || p.TTL != nil || p.Cursor != nil {
			return nil, errors.New("invalid unsubscribe parameters")
		}
		id, err := eventIdentity(eventOwner(f.token), p)
		if err != nil {
			return nil, err
		}
		if p.Delivery.URL != f.callback {
			return nil, errors.New("callback outside controlled sink")
		}
		eventMu.Lock()
		defer eventMu.Unlock()
		if err = f.remove(id); err != nil {
			return nil, errors.New("subscription removal failed")
		}
		return &eventEmptyResult{}, nil
	}); err != nil {
		panic("event registration failed")
	}
}
