package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"text/tabwriter"
)

// doctor enumerates each command's declared steps and probes every platform
// lib next to it, so coverage drift between bash and PowerShell is visible
// instead of silent. It also flags steps with no <step>_check function, a
// check whose body runs --apply (a check must be read-only), and, for this
// host, requires binaries that are not on PATH. Returns the exit code: 1 if
// a lib is missing a step or a check applies.

type libReport struct {
	Lib      string   `json:"lib"`
	Target   string   `json:"target"`
	Status   string   `json:"status"`
	Missing  []string `json:"missing,omitempty"`
	NoCheck  []string `json:"no_check,omitempty"`
	Applying []string `json:"check_runs_apply,omitempty"`
}

type commandReport struct {
	Name         string      `json:"name"`
	Source       string      `json:"source"`
	Libs         []libReport `json:"libs"`
	NotOnPath    []string    `json:"requires_not_on_path,omitempty"`
	NeedTerminal []string    `json:"terminal_steps,omitempty"`
}

func doctor(name string, asJSON bool, w io.Writer) int {
	cmds := discoverCommands(gitDir())
	if name != "" {
		var filtered []Command
		for _, c := range cmds {
			if c.Name == name {
				filtered = append(filtered, c)
			}
		}
		if len(filtered) == 0 {
			fmt.Fprintf(os.Stderr, "cmdr: unknown command %q\n", name)
			return 1
		}
		cmds = filtered
	}
	bad := false
	var reports []commandReport
	for _, c := range cmds {
		rep := commandReport{Name: c.Name, Source: c.Source}
		for _, s := range c.Steps {
			if bin := missingRequires(s); bin != "" {
				rep.NotOnPath = append(rep.NotOnPath, s.Name+" needs "+bin)
			}
			if s.Terminal {
				rep.NeedTerminal = append(rep.NeedTerminal, s.Name)
			}
		}
		for _, libName := range []string{"lib.sh", "lib.ps1"} {
			lib := filepath.Join(c.Dir, libName)
			lr := libReport{Lib: libName, Target: "darwin/linux"}
			libPlatforms := []string{"darwin", "linux"}
			if libName == "lib.ps1" {
				lr.Target = "windows"
				libPlatforms = []string{"windows"}
			}
			// A lib is only owed for platforms the command is gated to: a
			// linux-only command with no lib.ps1 is correct, not drift.
			if len(c.Platforms) > 0 && !platformsOverlap(c.Platforms, libPlatforms) {
				lr.Status = "n/a (command not gated to " + lr.Target + ")"
				rep.Libs = append(rep.Libs, lr)
				continue
			}
			if _, err := os.Stat(lib); err != nil {
				lr.Status = "missing entirely"
				bad = true
				rep.Libs = append(rep.Libs, lr)
				continue
			}
			funcs, err := declaredFuncs(lib)
			if err != nil {
				lr.Status = fmt.Sprintf("probe failed: %v", err)
				bad = true
				rep.Libs = append(rep.Libs, lr)
				continue
			}
			bodies := checkBodies(lib)
			for _, s := range c.Steps {
				fn := strings.ToLower(s.Name)
				if !funcs[fn] {
					lr.Missing = append(lr.Missing, s.Name)
				} else if !funcs[fn+"_check"] {
					lr.NoCheck = append(lr.NoCheck, s.Name)
				} else if strings.Contains(bodies[fn+"_check"], "--apply") {
					lr.Applying = append(lr.Applying, s.Name)
				}
			}
			lr.Status = "ok"
			if len(lr.Missing) > 0 {
				lr.Status = "missing: " + strings.Join(lr.Missing, ", ")
				bad = true
			}
			if len(lr.Applying) > 0 {
				bad = true
			}
			rep.Libs = append(rep.Libs, lr)
		}
		reports = append(reports, rep)
	}
	if asJSON {
		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		enc.Encode(reports)
	} else {
		renderDoctor(reports, w)
	}
	if bad {
		return 1
	}
	return 0
}

func renderDoctor(reports []commandReport, w io.Writer) {
	tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
	for _, rep := range reports {
		fmt.Fprintf(tw, "%s\t(from %s)\t\t\n", rep.Name, rep.Source)
		for _, lr := range rep.Libs {
			var notes []string
			if len(lr.NoCheck) > 0 {
				notes = append(notes, "no check: "+strings.Join(lr.NoCheck, ", "))
			}
			if len(lr.Applying) > 0 {
				notes = append(notes, "CHECK RUNS --apply: "+strings.Join(lr.Applying, ", "))
			}
			fmt.Fprintf(tw, "  %s\t%s\t%s\t%s\n", lr.Lib, lr.Target, lr.Status, strings.Join(notes, "; "))
		}
		if len(rep.NotOnPath) > 0 {
			fmt.Fprintf(tw, "  here\t%s\tnot on PATH: %s\t\n", shortHostname(), strings.Join(rep.NotOnPath, ", "))
		}
		if len(rep.NeedTerminal) > 0 {
			fmt.Fprintf(tw, "  terminal\t\tneeds the screen: %s\t\n", strings.Join(rep.NeedTerminal, ", "))
		}
	}
	tw.Flush()
}

var (
	bashFunc = regexp.MustCompile(`(?m)^\s*(?:function\s+)?([A-Za-z0-9_]+)\s*\(\)\s*\{`)
	psFunc   = regexp.MustCompile(`(?mi)^\s*function\s+([A-Za-z0-9_-]+)\s*\{`)
)

// checkBodies is a static read of a lib: function name -> its text up to the
// next function, enough to notice a check that shells out with --apply.
func checkBodies(lib string) map[string]string {
	data, err := os.ReadFile(lib)
	if err != nil {
		return nil
	}
	re := bashFunc
	if strings.HasSuffix(lib, ".ps1") {
		re = psFunc
	}
	text := string(data)
	locs := re.FindAllStringSubmatchIndex(text, -1)
	bodies := map[string]string{}
	for i, loc := range locs {
		end := len(text)
		if i+1 < len(locs) {
			end = locs[i+1][0]
		}
		bodies[strings.ToLower(text[loc[2]:loc[3]])] = text[loc[1]:end]
	}
	return bodies
}

func platformsOverlap(gated, libServes []string) bool {
	for _, p := range gated {
		for _, l := range libServes {
			if normPlatform(strings.ToLower(p)) == l {
				return true
			}
		}
	}
	return false
}
