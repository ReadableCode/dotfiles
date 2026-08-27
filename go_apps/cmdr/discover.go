package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// gitDir finds the directory holding the sibling repos. The shell already
// solved this - .shared_aliases / powershell_aliases resolve $gitDir through
// the context-shard candidates and export it - so the exported gitDir is the
// answer. Fallbacks, for running outside a configured shell: this binary's
// own location (it lives at <gitdir>/dotfiles/go_apps/cmdr/, so four parents
// up), then ~/GitHub.
// EVERY candidate must contain a dotfiles git checkout or the process exits:
// a guessed root once pointed the repo puller at a whole home directory.
// Never guess here again.
func gitDir() string {
	var candidates []string
	if d := os.Getenv("gitDir"); d != "" {
		candidates = append(candidates, d)
	} else {
		if exe, err := os.Executable(); err == nil {
			if resolved, err := filepath.EvalSymlinks(exe); err == nil {
				exe = resolved
			}
			candidates = append(candidates, filepath.Dir(filepath.Dir(filepath.Dir(filepath.Dir(exe)))))
		}
		if home, err := os.UserHomeDir(); err == nil {
			candidates = append(candidates, filepath.Join(home, "GitHub"))
		}
	}
	for _, c := range candidates {
		if _, err := os.Stat(filepath.Join(c, "dotfiles", ".git")); err == nil {
			return c
		}
	}
	fmt.Fprintf(os.Stderr,
		"cmdr: cannot locate the repos directory (tried %v; each must contain a dotfiles checkout).\n"+
			"Open a shell that sources the shared aliases so $gitDir is exported.\n", candidates)
	os.Exit(1)
	return ""
}

// discoverCommands globs <gitdir>/*/commands/*.cmd - the same sibling-repo
// discovery the deploy manifests use. A repo contributes commands without
// dotfiles knowing it exists, and a machine only has the repos it is
// entitled to, so it only discovers those commands. Zero sibling repos is
// fine: the built-ins (version, doctor, repos ensure) still work.
func discoverCommands(gitdir string) []Command {
	matches, _ := filepath.Glob(filepath.Join(gitdir, "*", "commands", "*.cmd"))
	sort.Strings(matches)
	seen := map[string]string{}
	var cmds []Command
	for _, path := range matches {
		c, err := parseCmdFile(path)
		if err != nil {
			fmt.Fprintln(os.Stderr, "cmdr: skipping bad definition:", err)
			continue
		}
		if prev, dup := seen[c.Name]; dup {
			fmt.Fprintf(os.Stderr, "cmdr: skipping %s from %s: already defined in %s\n", c.Name, c.Source, prev)
			continue
		}
		seen[c.Name] = c.Source
		cmds = append(cmds, c)
	}
	// Explicit order: comes from each .cmd file; alphabetical only breaks ties.
	sort.Slice(cmds, func(i, j int) bool {
		if cmds[i].Order != cmds[j].Order {
			return cmds[i].Order < cmds[j].Order
		}
		return cmds[i].Name < cmds[j].Name
	})
	return cmds
}
