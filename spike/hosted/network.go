package main

import (
	"crypto/tls"
	"crypto/x509"
	"errors"
	"net"
	"net/http"
	"os"
	"time"
)

// Uses the existing Go transport; WASIX requires the standard nonblocking flag.
func newHTTPClient() (*http.Client, error) {
	roots, err := x509.SystemCertPool()
	if err != nil {
		roots = x509.NewCertPool()
	}
	if path := os.Getenv("POC_CA_FILE"); path != "" {
		pem, err := os.ReadFile(path)
		if err != nil || !roots.AppendCertsFromPEM(pem) {
			return nil, errors.New("invalid configured CA bundle")
		}
	}
	dialer := &net.Dialer{Timeout: 5 * time.Second, Control: socketControl}
	return &http.Client{Timeout: 10 * time.Second, Transport: &http.Transport{
		Proxy: nil, DialContext: dialer.DialContext,
		TLSClientConfig:     &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
		TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 5 * time.Second,
		MaxConnsPerHost: 8, MaxIdleConnsPerHost: 4,
	}, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect refused") }}, nil
}
