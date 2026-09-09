package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"text/tabwriter"
)

// Every run writes ~/logs/cmdr/<command>-<mode>-<timestamp>.log (see
// runSteps) and ends it with a "result: ..." trailer, so a failure you only
// noticed later is still there to read.

func logsDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join(os.TempDir(), "cmdr-logs")
	}
	return filepath.Join(home, "logs", "cmdr")
}

type logEntry struct {
	Path    string
	Command string
	Mode    string
	Stamp   string
	Result  string
}

// parseLogName splits <command>-<mode>-<YYYYMMDD-HHMMSS>.log; command names
// may themselves contain dashes, so the split is from the right.
func parseLogName(path string) (logEntry, bool) {
	base := strings.TrimSuffix(filepath.Base(path), ".log")
	parts := strings.Split(base, "-")
	if len(parts) < 4 {
		return logEntry{}, false
	}
	stamp := parts[len(parts)-2] + "-" + parts[len(parts)-1]
	mode := parts[len(parts)-3]
	name := strings.Join(parts[:len(parts)-3], "-")
	if mode != "check" && mode != "apply" {
		return logEntry{}, false
	}
	return logEntry{Path: path, Command: name, Mode: mode, Stamp: stamp}, true
}

func logResult(path string) string {
	f, err := os.Open(path)
	if err != nil {
		return "?"
	}
	defer f.Close()
	result := "unfinished"
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	for sc.Scan() {
		if strings.HasPrefix(sc.Text(), "result: ") {
			result = strings.TrimPrefix(sc.Text(), "result: ")
		}
	}
	return result
}

// listLogs returns the run logs, newest first, optionally for one command.
func listLogs(command string) []logEntry {
	matches, _ := filepath.Glob(filepath.Join(logsDir(), "*.log"))
	var entries []logEntry
	for _, path := range matches {
		e, ok := parseLogName(path)
		if !ok || (command != "" && e.Command != command) {
			continue
		}
		e.Result = logResult(path)
		entries = append(entries, e)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Stamp > entries[j].Stamp })
	return entries
}

// showLogs: bare lists the newest runs; with a command prints its newest log
// in full (--list to list that command's runs instead).
func showLogs(args []string, w io.Writer) int {
	command := ""
	list := false
	for _, a := range args {
		if a == "--list" {
			list = true
		} else if strings.HasPrefix(a, "-") {
			fmt.Fprintf(os.Stderr, "cmdr: unknown flag %q\n", a)
			return 2
		} else {
			command = a
		}
	}
	entries := listLogs(command)
	if len(entries) == 0 {
		fmt.Fprintf(w, "no run logs in %s\n", logsDir())
		return 0
	}
	if command != "" && !list {
		data, err := os.ReadFile(entries[0].Path)
		if err != nil {
			fmt.Fprintln(os.Stderr, "cmdr:", err)
			return 1
		}
		fmt.Fprintf(w, "%s\n\n", entries[0].Path)
		w.Write(data)
		return 0
	}
	tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
	limit := 20
	if command != "" {
		limit = len(entries)
	}
	for i, e := range entries {
		if i >= limit {
			break
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\n", e.Stamp, e.Command, e.Mode, e.Result, e.Path)
	}
	tw.Flush()
	return 0
}
