package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

// The host harness supplies a loopback HTTPS server with an ephemeral CA.
func TestGuestNetwork(t *testing.T) {
	endpoint := os.Getenv("POC_NETWORK_TEST_URL")
	if endpoint == "" {
		t.Skip("requires independent synthetic HTTPS host")
	}
	client, err := newHTTPClient()
	if err != nil {
		t.Fatal(err)
	}
	defer client.CloseIdleConnections()
	check := func() error {
		res, err := client.Post(endpoint+"/echo", "text/plain", strings.NewReader("synthetic-nonce"))
		if err != nil {
			return err
		}
		defer res.Body.Close()
		body, err := io.ReadAll(io.LimitReader(res.Body, 128))
		if err != nil {
			return err
		}
		if res.StatusCode != 200 || string(body) != "synthetic-nonce" {
			return errors.New("echo mismatch")
		}
		return nil
	}
	if err := check(); err != nil {
		t.Fatal("DNS/TLS/HTTP:", err)
	}
	var wg sync.WaitGroup
	failures := make(chan error, 4)
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); failures <- check() }()
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		if err != nil {
			t.Error("concurrent request:", err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "GET", endpoint+"/slow", nil)
	start := time.Now()
	res, err := client.Do(req)
	if res != nil {
		res.Body.Close()
	}
	if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > 3*time.Second {
		t.Fatalf("cancellation: elapsed=%v err=%v", time.Since(start), err)
	}
	// Check certificates through the same configured Transport, not a separate TLS dial.
	for _, mode := range []string{"untrusted", "wrong-name"} {
		bad, err := newHTTPClient()
		if err != nil {
			t.Fatal(err)
		}
		tr := bad.Transport.(*http.Transport)
		if mode == "untrusted" {
			tr.TLSClientConfig = &tls.Config{RootCAs: x509.NewCertPool(), MinVersion: tls.VersionTLS12}
		} else {
			tr.TLSClientConfig.ServerName = "wrong.invalid"
		}
		res, err := bad.Get(endpoint + "/echo")
		if res != nil {
			res.Body.Close()
		}
		bad.CloseIdleConnections()
		if mode == "untrusted" {
			var target x509.UnknownAuthorityError
			if !errors.As(err, &target) {
				t.Fatalf("untrusted CA: %v", err)
			}
		} else {
			var target x509.HostnameError
			if !errors.As(err, &target) {
				t.Fatalf("wrong name: %v", err)
			}
		}
	}
}
