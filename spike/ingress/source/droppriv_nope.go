//go:build windows || wasip1
// +build windows wasip1

package main

import (
	"errors"
	"runtime"
)

func dropPrivileges(uid, gid int) error {
	return errors.New("setuid and setgid not supported on " + runtime.GOOS)
}
