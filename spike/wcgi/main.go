package main

import (
 "encoding/json"
 "io"
 "net/http"
 "net/http/cgi"
 "os"
)

func main() {
 err := cgi.Serve(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
  body, err := io.ReadAll(io.LimitReader(r.Body, 4097))
  if err != nil || len(body) > 4096 { http.Error(w, "invalid body", 400); return }
  w.Header().Set("Content-Type", "application/json")
  json.NewEncoder(w).Encode(map[string]string{"method":r.Method,"path":r.URL.Path,"body":string(body),"synthetic_header":r.Header.Get("X-Synthetic")})
 }))
 if err != nil { os.Stderr.WriteString(err.Error()); os.Exit(1) }
}
