package main

// Same-process, opt-in synthetic management surface; no production auth or DB.
import (
	"context"
	"flag"
	"fmt"
	"net"
	"net/http"
	"regexp"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var syntheticMCP = flag.Bool("synthetic-router-mcp", false, "enable loopback-only synthetic /mcp management (no durable DB or live delivery)")
var syntheticID = regexp.MustCompile(`^sub_[a-z0-9_-]{1,64}$`)

// Interfaces separate the receiver's read view from MCP's write capability.
// They are logical application boundaries, not database permissions.
type registrationReader interface {
	snapshot() ([]routePolicy, map[string]bool)
}
type registrationWriter struct{ registry *routeRegistry }

func (w registrationWriter) addSubscription(id string) error {
	if !syntheticID.MatchString(id) {
		return fmt.Errorf("subscription_id_invalid")
	}
	w.registry.Lock()
	defer w.registry.Unlock()
	if len(w.registry.subscriptions) >= 100 && !w.registry.subscriptions[id] {
		return fmt.Errorf("subscription_limit")
	}
	w.registry.subscriptions[id] = true
	return nil
}

type subscriptionInput struct {
	ID string `json:"id" jsonschema:"Synthetic registered subscription ID, starting sub_"`
}
type emptyInput struct{}
type subscriptionOutput struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}
type listOutput struct {
	IDs  []string `json:"ids"`
	Mode string   `json:"mode"`
}
type eventListParams struct{ mcp.ParamsBase }
type eventListResult struct {
	mcp.ResultBase
	Events []map[string]any `json:"events"`
}
type disabledEventParams struct{ mcp.ParamsBase }
type disabledEventResult struct{ mcp.ResultBase }

func syntheticMCPHandler(registry *routeRegistry) http.Handler {
	server := mcp.NewServer(&mcp.Implementation{Name: "synthetic-webhook-router", Version: "0.0.0-spike"}, nil)
	writer := registrationWriter{registry}
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_subscription_create", Description: "Register an ID for local dry-run routing only; never creates or verifies a live callback."},
		func(ctx context.Context, req *mcp.CallToolRequest, in subscriptionInput) (*mcp.CallToolResult, subscriptionOutput, error) {
			err := writer.addSubscription(in.ID)
			return nil, subscriptionOutput{ID: in.ID, Status: "dry_run"}, err
		})
	mcp.AddTool(server, &mcp.Tool{Name: "synthetic_subscription_list", Description: "Read process-local synthetic IDs. State is not durable."},
		func(ctx context.Context, req *mcp.CallToolRequest, in emptyInput) (*mcp.CallToolResult, listOutput, error) {
			_, subs := registry.snapshot()
			ids := []string{}
			for id, active := range subs {
				if active {
					ids = append(ids, id)
				}
			}
			return nil, listOutput{IDs: ids, Mode: "synthetic-dry-run"}, nil
		})
	// Event catalog shape follows inspected WeeChat source. Top-level Events
	// discovery and live callback lifecycle remain deliberately unimplemented.
	if err := mcp.AddReceivingCustomMethod(server, "events/list", func(ctx context.Context, session *mcp.ServerSession, in *eventListParams) (*eventListResult, error) {
		return &eventListResult{Events: []map[string]any{{"name": "webhook.received", "delivery": []string{"webhook"}, "inputSchema": map[string]any{"type": "object"}, "payloadSchema": map[string]any{"type": "object"}}}}, nil
	}); err != nil {
		panic(err)
	}
	for _, name := range []string{"events/subscribe", "events/unsubscribe"} {
		if err := mcp.AddReceivingCustomMethod(server, name, func(ctx context.Context, session *mcp.ServerSession, in *disabledEventParams) (*disabledEventResult, error) {
			return nil, fmt.Errorf("live event subscription lifecycle disabled; use synthetic tools")
		}); err != nil {
			panic(err)
		}
	}
	handler := mcp.NewStreamableHTTPHandler(func(r *http.Request) *mcp.Server { return server }, &mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil || !net.ParseIP(host).IsLoopback() || r.Header.Get("Origin") != "" {
			http.Error(w, "synthetic_loopback_only", 403)
			return
		}
		if r.Method != "POST" {
			http.Error(w, "synthetic_post_only", 405)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 65536)
		handler.ServeHTTP(w, r)
	})
}
