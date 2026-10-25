// Existing WASIX Go toolchain probe; no custom networking adapter.
package main

import (
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	mode, addr := os.Args[1], os.Args[2]
	if mode == "tcp" {
		c, e := net.DialTimeout("tcp", addr, 5*time.Second)
		if e != nil {
			return e
		}
		defer c.Close()
		c.SetDeadline(time.Now().Add(5 * time.Second))
		io.WriteString(c, "synthetic-nonce")
		b := make([]byte, 15)
		_, e = io.ReadFull(c, b)
		if e != nil {
			return e
		}
		if string(b) != "synthetic-nonce" {
			return errors.New("echo mismatch")
		}
		fmt.Println("PASS tcp")
		return nil
	}
	roots := x509.NewCertPool()
	pem, e := os.ReadFile("/fixtures/cert.pem")
	if e != nil {
		return e
	}
	if mode != "untrusted" && !roots.AppendCertsFromPEM(pem) {
		return errors.New("invalid test CA")
	}
	cfg := &tls.Config{RootCAs: roots, ServerName: "localhost", MinVersion: tls.VersionTLS12}
	if mode == "wrong-name" {
		cfg.ServerName = "wrong.invalid"
	}
	if mode != "https" {
		c, e := tls.DialWithDialer(&net.Dialer{Timeout: 5 * time.Second}, "tcp", addr, cfg)
		if c != nil {
			c.Close()
		}
		if mode == "untrusted" {
			var unknown x509.UnknownAuthorityError
			if !errors.As(e, &unknown) {
				return fmt.Errorf("expected unknown authority, got %v", e)
			}
		} else if mode == "wrong-name" {
			var wrong x509.HostnameError
			if !errors.As(e, &wrong) {
				return fmt.Errorf("expected hostname rejection, got %v", e)
			}
		} else if e != nil {
			return e
		}
		fmt.Println("PASS", mode)
		return nil
	}
	client := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: cfg, Proxy: nil}, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect") }}
	resp, e := client.Post("https://"+addr+"/synthetic", "text/plain", strings.NewReader("synthetic-nonce"))
	if e != nil {
		return e
	}
	defer resp.Body.Close()
	body, e := io.ReadAll(io.LimitReader(resp.Body, 128))
	if e != nil {
		return e
	}
	if resp.StatusCode != 200 || string(body) != "synthetic-nonce" {
		return errors.New("HTTP receipt mismatch")
	}
	fmt.Println("PASS https")
	return nil
}
