//go:build !wasip1

package main

import "syscall"

func socketControl(network, address string, raw syscall.RawConn) error { return nil }
