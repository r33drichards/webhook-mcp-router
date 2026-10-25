//go:build wasip1

package main

import "syscall"

func socketControl(network, address string, raw syscall.RawConn) error {
	var inner error
	if err := raw.Control(func(fd uintptr) { inner = syscall.SetNonblock(int(fd), true) }); err != nil {
		return err
	}
	return inner
}
