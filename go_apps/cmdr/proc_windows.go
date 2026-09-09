//go:build windows

package main

import "os/exec"

// No process groups to speak of on Windows: the shell is killed and its
// children are on their own. Good enough for a v0 kill; job objects later.
func setProcessGroup(cmd *exec.Cmd) {}

func killProcess(cmd *exec.Cmd) {
	if cmd.Process != nil {
		_ = cmd.Process.Kill()
	}
}
