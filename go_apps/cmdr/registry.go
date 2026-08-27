package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// A Step is a function name plus optional PATH-lookup preconditions.
// requires= is a PATH lookup ONLY - the core never probes for privileges
// (some fleet hosts alert on every failed sudo).
type Step struct {
	Name     string
	Requires []string
}

// A Command is the core's whole view of a unit of work: where it came from,
// who may run it, and the ordered step names. What the steps DO lives in the
// platform libs next to the .cmd file - the core never knows.
type Command struct {
	Name         string
	Description  string
	Order        int // display/sort position; lower first, default 1000
	Platforms    []string
	Hosts        []string
	ExcludeHosts []string
	Steps        []Step
	Dir          string // the commands/ dir holding the .cmd and its libs
	Source       string // sibling repo it was discovered in
}

// parseCmdFile reads the shared artifact: gating headers, then an ordered
// list of step names. Plain text on purpose - no DSL, nothing generated.
func parseCmdFile(path string) (Command, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Command{}, err
	}
	c := Command{
		Name:  strings.TrimSuffix(filepath.Base(path), ".cmd"),
		Dir:   filepath.Dir(path),
		Order: 1000,
	}
	c.Source = filepath.Base(filepath.Dir(c.Dir))
	inSteps := false
	for i, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if !inSteps {
			key, val, found := strings.Cut(line, ":")
			if !found {
				return c, fmt.Errorf("%s:%d: expected 'key: value' before steps:", path, i+1)
			}
			val = strings.TrimSpace(val)
			switch strings.TrimSpace(key) {
			case "description":
				c.Description = val
			case "order":
				n, convErr := strconv.Atoi(val)
				if convErr != nil {
					return c, fmt.Errorf("%s:%d: order must be an integer, got %q", path, i+1, val)
				}
				c.Order = n
			case "platforms":
				c.Platforms = splitList(val)
			case "hosts":
				c.Hosts = splitList(val)
			case "exclude_hosts":
				c.ExcludeHosts = splitList(val)
			case "steps":
				inSteps = true
			default:
				return c, fmt.Errorf("%s:%d: unknown key %q", path, i+1, key)
			}
			continue
		}
		fields := strings.Fields(line)
		step := Step{Name: fields[0]}
		for _, opt := range fields[1:] {
			k, v, _ := strings.Cut(opt, "=")
			if k != "requires" {
				return c, fmt.Errorf("%s:%d: unknown step option %q", path, i+1, opt)
			}
			step.Requires = append(step.Requires, splitList(v)...)
		}
		c.Steps = append(c.Steps, step)
	}
	if len(c.Steps) == 0 {
		return c, fmt.Errorf("%s: no steps", path)
	}
	return c, nil
}

func splitList(s string) []string {
	return strings.FieldsFunc(s, func(r rune) bool { return r == ' ' || r == ',' })
}
