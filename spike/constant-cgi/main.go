// Constant CGI comparison: standard library only, no fixture or storage access.
package main

import (
	"io"
	"net/http"
	"net/http/cgi"
	"os"
)

func main() {
	err := cgi.Serve(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		if r.Method == http.MethodGet && r.URL.Path == "/_poc/health" {
			_, _ = io.WriteString(w, `{"status":"runtime-ready"}`)
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, `{"error":"POC_DIAGNOSTIC_ONLY"}`)
	}))
	if err != nil {
		_, _ = os.Stderr.WriteString("POC_CGI_SERVE_FAILED\n")
		os.Exit(1)
	}
}
