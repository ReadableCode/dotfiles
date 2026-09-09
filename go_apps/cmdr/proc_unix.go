//go:build !windows

package main

import (
	"os/exec"
	"syscall"
	"time"
)

// setProcessGroup puts a step's shell in its own process group so a kill
// reaches the python/rsync/whatever it spawned, not just the shell.
func setProcessGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

// killProcess asks the whole group to stop, then insists two seconds later.
func killProcess(cmd *exec.Cmd) {
	if cmd.Process == nil {
		return
	}
	pgid := -cmd.Process.Pid
	_ = syscall.Kill(pgid, syscall.SIGTERM)
	go func() {
		time.Sleep(2 * time.Second)
		_ = syscall.Kill(pgid, syscall.SIGKILL)
	}()
}
