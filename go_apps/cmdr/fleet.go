package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"text/tabwriter"
	"time"
)

// fleet runs one command's check on every inventory host over ssh and prints
// a table. Hosts and their ssh command lines come from src/ssh_aliases.py
// --format hosts, the single implementation of the inventory's ssh rules
// (jumps, ports, users), so this never re-derives them. Check only:
// applying across the fleet from one keypress is not a feature.

type fleetHost struct {
	Host    string `json:"host"`
	OS      string `json:"os"`
	Command string `json:"command"`
}

func fleetHosts(gitdir string) ([]fleetHost, error) {
	script := filepath.Join(gitdir, "dotfiles", "src", "ssh_aliases.py")
	out, err := exec.Command("python3", script, "--format", "hosts", "--root", gitdir).Output()
	if err != nil {
		return nil, fmt.Errorf("listing hosts via %s: %w", script, err)
	}
	var all []fleetHost
	if err := json.Unmarshal(out, &all); err != nil {
		return nil, fmt.Errorf("parsing host list: %w", err)
	}
	local := shortHostname()
	var hosts []fleetHost
	for _, h := range all {
		if strings.ToLower(strings.Split(h.Host, ".")[0]) == local {
			continue
		}
		switch h.OS {
		case "macos", "linux", "windows":
		default:
			continue // phones and appliances have no cmdr
		}
		hosts = append(hosts, h)
	}
	sort.Slice(hosts, func(i, j int) bool { return strings.ToLower(hosts[i].Host) < strings.ToLower(hosts[j].Host) })
	return hosts, nil
}

// remoteCheck is what the far side runs. Interactive shells on purpose: the
// cmdr shim is a function the interactive rc files define, and it rebuilds
// the binary there when the sources moved.
func remoteCheck(h fleetHost, name string) string {
	if h.OS == "windows" {
		return fmt.Sprintf(`powershell -NoLogo -Command "cmdr %s --check"`, name)
	}
	return fmt.Sprintf(`$SHELL -ic 'cmdr %s --check' 2>&1`, name)
}

type fleetResult struct {
	Host   string
	OS     string
	Status string
	Last   string
	Log    string
}

func fleetRun(h fleetHost, name string) fleetResult {
	words := strings.Fields(h.Command)
	args := append(words[1:len(words)-1], "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", words[len(words)-1], remoteCheck(h, name))
	cmd := exec.Command(words[0], args...)
	var buf bytes.Buffer
	cmd.Stdout, cmd.Stderr = &buf, &buf
	err := cmd.Run()
	res := fleetResult{Host: h.Host, OS: h.OS}
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")
	res.Last = strings.TrimSpace(lines[len(lines)-1])
	if len(res.Last) > 70 {
		res.Last = res.Last[:70] + "…"
	}
	path := filepath.Join(logsDir(), fmt.Sprintf("fleet-%s-%s-%s.log", name, strings.ToLower(h.Host), time.Now().Format("20060102-150405")))
	if os.MkdirAll(logsDir(), 0o755) == nil && os.WriteFile(path, buf.Bytes(), 0o644) == nil {
		res.Log = path
	}
	switch {
	case err == nil:
		res.Status = "ok"
	case exitCode(err) == 1:
		res.Status = "drift"
	case exitCode(err) == 127 || strings.Contains(res.Last, "cmdr: command not found") ||
		strings.Contains(res.Last, "command not found: cmdr"):
		res.Status = "no cmdr" // the shim is not in that user's shell: dotfiles not deployed there
	case exitCode(err) == 255:
		res.Status = "unreachable"
	default:
		res.Status = "failed"
	}
	return res
}

func exitCode(err error) int {
	if ee, ok := err.(*exec.ExitError); ok {
		return ee.ExitCode()
	}
	return -1
}

func fleetCheck(name string, w io.Writer) int {
	gitdir := gitDir()
	found := false
	for _, c := range discoverCommands(gitdir) {
		if c.Name == name {
			found = true
		}
	}
	if !found {
		fmt.Fprintf(os.Stderr, "cmdr: unknown command %q (try 'cmdr commands')\n", name)
		return 1
	}
	hosts, err := fleetHosts(gitdir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "cmdr:", err)
		return 1
	}
	if len(hosts) == 0 {
		fmt.Fprintln(w, "no other ssh-reachable hosts in the inventories")
		return 0
	}
	fmt.Fprintf(w, "checking %s on %d hosts (this one, %s, excluded)...\n", name, len(hosts), shortHostname())
	results := make([]fleetResult, len(hosts))
	var wg sync.WaitGroup
	slots := make(chan struct{}, 8)
	for i, h := range hosts {
		wg.Add(1)
		go func(i int, h fleetHost) {
			defer wg.Done()
			slots <- struct{}{}
			results[i] = fleetRun(h, name)
			<-slots
		}(i, h)
	}
	wg.Wait()
	sty := newStyler(w)
	tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
	bad := false
	for _, r := range results {
		status := r.Status
		switch status {
		case "ok":
			status = sty.good(status)
		case "drift":
			status = sty.warn(status)
			bad = true
		default:
			status = sty.bad(status)
			bad = true
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\n", r.Host, r.OS, status, r.Last)
	}
	tw.Flush()
	fmt.Fprintf(w, "per-host output: %s\n", filepath.Join(logsDir(), "fleet-"+name+"-*.log"))
	if bad {
		return 1
	}
	return 0
}
