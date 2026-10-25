package main

import (
	"context"
	"fmt"
	"github.com/modelcontextprotocol/go-sdk/mcp"
	"net/http"
	"net/http/cgi"
	"os"
)

type idInput struct {
	ID string `json:"id"`
}
type emitInput struct {
	SubscriptionID string `json:"subscription_id"`
	Nonce          string `json:"nonce"`
}
type emptyInput struct{}
type output map[string]any

func handler(f *fixture) http.Handler {
	server := mcp.NewServer(&mcp.Implementation{Name: "synthetic-wcgi-events-poc", Version: "0.0.1"}, nil)
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
	mux.HandleFunc("/callback", f.callbackHandler)
	mux.HandleFunc("/receipts", f.receiptHandler)
	return mux
}
func main() {
	f, err := loadFixture()
	if err == nil {
		err = cgi.Serve(handler(f))
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "synthetic CGI configuration or execution failed")
		os.Exit(1)
	}
}
