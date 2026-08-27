package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"
)

const version = "0.1.0"

func usage() {
	fmt.Print(`cmdr - one entry point for fleet operations

usage:
  cmdr                      open the TUI
  cmdr commands             list discovered commands and their gating
  cmdr doctor [command]     probe platform libs for missing step functions
  cmdr repos ensure         clone missing repos (built in, works pre-discovery)
  cmdr <command>            show the plan, ask, then apply
  cmdr <command> --check    report drift, change nothing, exit 1 if drift
  cmdr <command> --yes      apply without prompting
  cmdr version
`)
}

func parseFlags(args []string) (check, yes bool, err error) {
	for _, a := range args {
		switch a {
		case "--check":
			check = true
		case "--yes":
			yes = true
		default:
			return false, false, fmt.Errorf("unknown flag %q", a)
		}
	}
	if check && yes {
		return false, false, fmt.Errorf("--check and --yes are mutually exclusive")
	}
	return check, yes, nil
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
		listCommands()
	case "doctor":
		name := ""
		if len(args) > 1 {
			name = args[1]
		}
		os.Exit(doctor(name, os.Stdout))
	case "repos":
		if len(args) < 2 || args[1] != "ensure" {
			fmt.Fprintln(os.Stderr, "usage: cmdr repos ensure [--check|--yes]")
			os.Exit(2)
		}
		check, yes, err := parseFlags(args[2:])
		if err != nil {
			fmt.Fprintln(os.Stderr, "cmdr:", err)
			os.Exit(2)
		}
		os.Exit(reposEnsure(check, yes))
	default:
		os.Exit(dispatch(args[0], args[1:]))
	}
}

func dispatch(name string, rest []string) int {
	check, yes, err := parseFlags(rest)
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
	if check {
		drift, err := runSteps(*found, ModeCheck, os.Stdout, os.Stderr, os.Stdin)
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
		showPlan(*found)
		if !confirm("apply? [y/N] ") {
			fmt.Println("aborted, nothing changed")
			return 0
		}
	}
	if _, err := runSteps(*found, ModeApply, os.Stdout, os.Stderr, os.Stdin); err != nil {
		fmt.Fprintln(os.Stderr, "cmdr:", err)
		return 1
	}
	return 0
}

func showPlan(c Command) {
	fmt.Printf("%s - %s\n", c.Name, c.Description)
	fmt.Printf("from %s, lib %s\n", c.Source, filepath.Base(libFor(c.Dir, currentPlatform())))
	fmt.Println("steps, in order:")
	for _, s := range c.Steps {
		line := "  " + s.Name
		if len(s.Requires) > 0 {
			line += "  (requires " + strings.Join(s.Requires, ", ") + " on PATH)"
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

func listCommands() {
	cmds := discoverCommands(gitDir())
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
