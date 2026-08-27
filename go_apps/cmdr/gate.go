package main

import (
	"os"
	"runtime"
	"strings"
)

// currentPlatform returns darwin, linux, or windows - runtime.GOOS already
// uses the same tokens as the deploy manifests.
func currentPlatform() string {
	return runtime.GOOS
}

// normPlatform accepts "mac" as an alias for darwin, matching the variant
// tokens deploy_configs.py resolves.
func normPlatform(p string) string {
	if p == "mac" {
		return "darwin"
	}
	return p
}

func shortHostname() string {
	h, err := os.Hostname()
	if err != nil {
		return ""
	}
	h, _, _ = strings.Cut(h, ".")
	return strings.ToLower(h)
}

func matchHost(list []string, host string) bool {
	for _, h := range list {
		if strings.ToLower(h) == host {
			return true
		}
	}
	return false
}

// applicable mirrors personal_repos.yaml semantics: exclude_hosts is checked
// first and wins, hosts is an allow list, empty means everywhere, and
// platforms filter on top. One scoping model across configs, repos, and
// commands.
func applicable(c Command) (bool, string) {
	host := shortHostname()
	if matchHost(c.ExcludeHosts, host) {
		return false, "excluded on host " + host
	}
	if len(c.Hosts) > 0 && !matchHost(c.Hosts, host) {
		return false, "host " + host + " not in hosts list"
	}
	if len(c.Platforms) > 0 {
		ok := false
		for _, p := range c.Platforms {
			if normPlatform(strings.ToLower(p)) == currentPlatform() {
				ok = true
			}
		}
		if !ok {
			return false, "not for platform " + currentPlatform()
		}
	}
	return true, ""
}
