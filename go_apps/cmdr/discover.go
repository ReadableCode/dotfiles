package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// gitDir finds the directory holding the sibling repos (~/GitHub on most
// machines). Order: explicit override, then walking up from cwd looking for
// the dotfiles checkout, then the default.
func gitDir() string {
	if d := os.Getenv("CMDR_GIT_DIR"); d != "" {
		return d
	}
	if wd, err := os.Getwd(); err == nil {
		for dir := wd; ; dir = filepath.Dir(dir) {
			if _, err := os.Stat(filepath.Join(dir, "dotfiles", "deploy_manifest.yaml")); err == nil {
				return dir
			}
			if dir == filepath.Dir(dir) {
				break
			}
		}
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "GitHub")
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
	return cmds
}
