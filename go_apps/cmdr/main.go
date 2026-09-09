package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"
)

const version = "0.2.0"

func usage() {
	fmt.Print(`cmdr - one entry point for fleet operations

usage:
  cmdr                          open the TUI
  cmdr commands [--json]        list discovered commands and their gating
  cmdr doctor [command] [--json] probe platform libs: missing steps, checks that apply, PATH
  cmdr repos ensure             clone missing repos (built in, works pre-discovery)
  cmdr <command> [args...]      show the plan, ask, then apply
  cmdr <command> --check        report drift, change nothing, exit 1 if drift
  cmdr <command> --yes          apply without prompting
  cmdr logs [command] [--list]  run logs (~/logs/cmdr): newest runs, or one command's latest log
  cmdr fleet <command>          run the command's check on every inventory host over ssh
  cmdr version

positional args after a command reach its steps as CMDR_ARG1..N (CMDR_ARGC).
`)
}

// parseFlags splits a command's arguments into the two flags and the
// positional arguments that reach the steps. Unknown flags are errors.
func parseFlags(args []string) (check, yes bool, rest []string, err error) {
	for _, a := range args {
		switch {
		case a == "--check":
			check = true
		case a == "--yes":
			yes = true
		case strings.HasPrefix(a, "-"):
			return false, false, nil, fmt.Errorf("unknown flag %q", a)
		default:
			rest = append(rest, a)
		}
	}
	if check && yes {
		return false, false, nil, fmt.Errorf("--check and --yes are mutually exclusive")
	}
	return check, yes, rest, nil
}

func hasFlag(args []string, flag string) bool {
	for _, a := range args {
		if a == flag {
			return true
		}
	}
	return false
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		if err := runTUI(); err != nil {
			fmt.Fprintln(os.Stderr, "cmdr:", err)
			os.Exit(1)
		}
		return
	}
	switch args[0] {
	case "version", "--version":
		fmt.Println("cmdr", version)
	case "help", "--help", "-h":
		usage()
	case "commands":
		listCommands(hasFlag(args[1:], "--json"))
	case "doctor":
		name := ""
		for _, a := range args[1:] {
			if !strings.HasPrefix(a, "-") {
				name = a
			}
		}
		os.Exit(doctor(name, hasFlag(args[1:], "--json"), os.Stdout))
	case "logs":
		os.Exit(showLogs(args[1:], os.Stdout))
	case "fleet":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "usage: cmdr fleet <command>")
			os.Exit(2)
		}
		os.Exit(fleetCheck(args[1], os.Stdout))
	case "repos":
		if len(args) < 2 || args[1] != "ensure" {
			fmt.Fprintln(os.Stderr, "usage: cmdr repos ensure [--check|--yes]")
			os.Exit(2)
		}
		check, yes, rest, err := parseFlags(args[2:])
		if err == nil && len(rest) > 0 {
			err = fmt.Errorf("repos ensure takes no arguments")
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "cmdr:", err)
			os.Exit(2)
		}
		os.Exit(reposEnsure(check, yes))
	default:
		code := dispatch(args[0], args[1:])
		if os.Getenv("CMDR_HANDOFF") != "" {
			waitForReturn(code)
		}
		os.Exit(code)
	}
}

// waitForReturn holds the screen after a command the TUI handed the terminal
// to. The TUI's alternate screen comes back the instant this process exits
// and wipes everything the command printed - a check's plan, a failure's
// traceback - so a handed-off run ends by waiting for enter instead.
func waitForReturn(code int) {
	sty := newStyler(os.Stdout)
	fmt.Println()
	if code == 0 {
		fmt.Println(sty.good("-- done") + sty.dim("  press enter to return to cmdr"))
	} else {
		fmt.Println(sty.bad(fmt.Sprintf("-- exited with status %d", code)) + sty.dim("  press enter to return to cmdr"))
	}
	bufio.NewScanner(os.Stdin).Scan()
}

func dispatch(name string, rest []string) int {
	check, yes, args, err := parseFlags(rest)
	if err != nil {
		fmt.Fprintln(os.Stderr, "cmdr:", err)
		return 2
	}
	cmds := discoverCommands(gitDir())
	var found *Command
	for i := range cmds {
		if cmds[i].Name == name {
			found = &cmds[i]
		}
	}
	if found == nil {
		fmt.Fprintf(os.Stderr, "cmdr: unknown command %q (try 'cmdr commands')\n", name)
		return 1
	}
	if ok, reason := applicable(*found); !ok {
		fmt.Fprintf(os.Stderr, "cmdr: %s does not run here: %s\n", name, reason)
		return 1
	}
	r := &runner{}
	if check {
		drift, err := runSteps(*found, ModeCheck, os.Stdout, os.Stderr, os.Stdin, args, r)
		if err != nil {
			fmt.Fprintln(os.Stderr, "cmdr:", err)
			return 1
		}
		if drift {
			return 1
		}
		return 0
	}
	if !yes {
		showPlan(*found, args)
		if !confirm("apply? [y/N] ") {
			fmt.Println("aborted, nothing changed")
			return 0
		}
	}
	if _, err := runSteps(*found, ModeApply, os.Stdout, os.Stderr, os.Stdin, args, r); err != nil {
		fmt.Fprintln(os.Stderr, "cmdr:", err)
		if r.LogPath != "" {
			fmt.Fprintln(os.Stderr, "log:", r.LogPath)
		}
		return 1
	}
	return 0
}

func showPlan(c Command, args []string) {
	fmt.Printf("%s - %s\n", c.Name, c.Description)
	fmt.Printf("from %s, lib %s\n", c.Source, filepath.Base(libFor(c.Dir, currentPlatform())))
	if len(args) > 0 {
		fmt.Printf("args: %s\n", strings.Join(args, " "))
	}
	fmt.Println("steps, in order:")
	for _, s := range c.Steps {
		line := "  " + s.Name
		if len(s.Requires) > 0 {
			line += "  (requires " + strings.Join(s.Requires, ", ") + " on PATH)"
		}
		if s.Terminal {
			line += "  (needs the terminal)"
		}
		fmt.Println(line)
	}
}

func confirm(prompt string) bool {
	fmt.Print(prompt)
	sc := bufio.NewScanner(os.Stdin)
	if !sc.Scan() {
		return false
	}
	answer := strings.ToLower(strings.TrimSpace(sc.Text()))
	return answer == "y" || answer == "yes"
}

type commandListing struct {
	Name        string   `json:"name"`
	Source      string   `json:"source"`
	Description string   `json:"description"`
	Order       int      `json:"order"`
	Platforms   []string `json:"platforms,omitempty"`
	Hosts       []string `json:"hosts,omitempty"`
	Steps       []string `json:"steps"`
	Terminal    bool     `json:"terminal"`
	Applicable  bool     `json:"applicable_here"`
	Reason      string   `json:"gated_reason,omitempty"`
}

func listCommands(asJSON bool) {
	cmds := discoverCommands(gitDir())
	if asJSON {
		var out []commandListing
		for _, c := range cmds {
			ok, reason := applicable(c)
			var steps []string
			for _, s := range c.Steps {
				steps = append(steps, s.Name)
			}
			out = append(out, commandListing{c.Name, c.Source, c.Description, c.Order, c.Platforms, c.Hosts, steps,
				c.needsTerminal(), ok, reason})
		}
		if out == nil {
			out = []commandListing{}
		}
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		enc.Encode(out)
		return
	}
	if len(cmds) == 0 {
		fmt.Println("no commands discovered (no sibling repos with a commands/ dir)")
		return
	}
	w := tabwriter.NewWriter(os.Stdout, 0, 4, 2, ' ', 0)
	for _, c := range cmds {
		status := "ok"
		if ok, reason := applicable(c); !ok {
			status = "gated: " + reason
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\n", c.Name, c.Source, status, c.Description)
	}
	w.Flush()
}
