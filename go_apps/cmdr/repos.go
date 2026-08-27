package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// repos ensure is built into the core, not discovered: a fresh machine has
// to be able to clone repos before any sibling repo (or interpreter) exists.

type repoEntry struct {
	Name         string   `yaml:"name"`
	Provider     string   `yaml:"provider"`
	Org          string   `yaml:"org"`
	SSHKey       string   `yaml:"ssh_key"`
	Dir          string   `yaml:"dir"`
	Hosts        []string `yaml:"hosts"`
	ExcludeHosts []string `yaml:"exclude_hosts"`
}

type repoConfig struct {
	Defaults repoEntry   `yaml:"defaults"`
	Repos    []repoEntry `yaml:"repos"`
}

// repoConfigFiles mirrors clone_repos.py discovery: every sibling repo may
// declare <context>_repos.yaml, where context is the dir name minus any
// _credentials suffix (personal_credentials/personal_repos.yaml,
// dotfiles/dotfiles_repos.yaml).
func repoConfigFiles(gitdir string) []string {
	entries, err := os.ReadDir(gitdir)
	if err != nil {
		return nil
	}
	var files []string
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		ctx := strings.TrimSuffix(e.Name(), "_credentials")
		p := filepath.Join(gitdir, e.Name(), ctx+"_repos.yaml")
		if _, err := os.Stat(p); err == nil {
			files = append(files, p)
		}
	}
	return files
}

func loadRepoEntries(gitdir string) ([]repoEntry, error) {
	declaredIn := map[string]string{}
	var all []repoEntry
	for _, path := range repoConfigFiles(gitdir) {
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		var cfg repoConfig
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		for _, r := range cfg.Repos {
			if r.Provider == "" {
				r.Provider = cfg.Defaults.Provider
			}
			if r.Org == "" {
				r.Org = cfg.Defaults.Org
			}
			if r.SSHKey == "" {
				r.SSHKey = cfg.Defaults.SSHKey
			}
			if r.Dir == "" {
				r.Dir = r.Name
			}
			// clone_repos.py fails loudly on duplicate declarations; so do we.
			if prev, dup := declaredIn[r.Name]; dup {
				return nil, fmt.Errorf("repo %s declared in both %s and %s", r.Name, prev, path)
			}
			declaredIn[r.Name] = path
			all = append(all, r)
		}
	}
	return all, nil
}

func repoWantedHere(r repoEntry) bool {
	host := shortHostname()
	if matchHost(r.ExcludeHosts, host) {
		return false
	}
	return len(r.Hosts) == 0 || matchHost(r.Hosts, host)
}

func cloneURL(r repoEntry) string {
	hostname := "github.com"
	if r.Provider == "bitbucket" {
		hostname = "bitbucket.org"
	}
	return fmt.Sprintf("git@%s:%s/%s.git", hostname, r.Org, r.Name)
}

func cloneRepo(gitdir string, r repoEntry) error {
	dest := filepath.Join(gitdir, r.Dir)
	cmd := exec.Command("git", "clone", cloneURL(r), dest)
	cmd.Stdout, cmd.Stderr, cmd.Stdin = os.Stdout, os.Stderr, os.Stdin
	sshCmd := ""
	if r.SSHKey != "" {
		key := r.SSHKey
		if strings.HasPrefix(key, "~") {
			home, _ := os.UserHomeDir()
			key = filepath.Join(home, key[1:])
		}
		sshCmd = fmt.Sprintf("ssh -i %s -o IdentitiesOnly=yes", key)
		cmd.Env = append(os.Environ(), "GIT_SSH_COMMAND="+sshCmd)
	}
	if err := cmd.Run(); err != nil {
		return err
	}
	if sshCmd != "" {
		// Pin the key into the clone so later pulls and pushes use it too.
		return exec.Command("git", "-C", dest, "config", "core.sshCommand", sshCmd).Run()
	}
	return nil
}

func reposEnsure(check, yes bool) int {
	gitdir := gitDir()
	entries, err := loadRepoEntries(gitdir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "cmdr:", err)
		return 1
	}
	if len(entries) == 0 {
		fmt.Println("no repo configs found (fresh machine? clone dotfiles and a credentials repo first)")
		return 0
	}
	var missing []repoEntry
	for _, r := range entries {
		if !repoWantedHere(r) {
			continue
		}
		if _, err := os.Stat(filepath.Join(gitdir, r.Dir)); err != nil {
			missing = append(missing, r)
		}
	}
	if len(missing) == 0 {
		fmt.Println("all entitled repos present")
		return 0
	}
	for _, r := range missing {
		fmt.Printf("missing: %s (%s)\n", r.Dir, cloneURL(r))
	}
	if check {
		return 1
	}
	failed := false
	for _, r := range missing {
		// Nothing clones without a yes - same contract as clone_repos.py.
		if !yes && !confirm(fmt.Sprintf("clone %s? [y/N] ", r.Dir)) {
			continue
		}
		if err := cloneRepo(gitdir, r); err != nil {
			fmt.Fprintf(os.Stderr, "cmdr: clone %s: %v\n", r.Dir, err)
			failed = true
		}
	}
	if failed {
		return 1
	}
	return 0
}
