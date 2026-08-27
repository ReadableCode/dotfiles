package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"
)

// doctor enumerates each command's declared steps and probes every platform
// lib next to it, so coverage drift between bash and PowerShell is visible
// instead of silent. Also flags steps with no <step>_check function.
// Returns the process exit code: 1 if anything is missing.
func doctor(name string, w io.Writer) int {
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
	tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
	for _, c := range cmds {
		fmt.Fprintf(tw, "%s\t(from %s)\t\t\n", c.Name, c.Source)
		for _, libName := range []string{"lib.sh", "lib.ps1"} {
			lib := filepath.Join(c.Dir, libName)
			target := "darwin/linux"
			if libName == "lib.ps1" {
				target = "windows"
			}
			if _, err := os.Stat(lib); err != nil {
				fmt.Fprintf(tw, "  %s\t%s\tmissing entirely\t\n", libName, target)
				bad = true
				continue
			}
			funcs, err := declaredFuncs(lib)
			if err != nil {
				fmt.Fprintf(tw, "  %s\t%s\tprobe failed: %v\t\n", libName, target, err)
				bad = true
				continue
			}
			var missing, nocheck []string
			for _, s := range c.Steps {
				fn := strings.ToLower(s.Name)
				if !funcs[fn] {
					missing = append(missing, s.Name)
				} else if !funcs[fn+"_check"] {
					nocheck = append(nocheck, s.Name)
				}
			}
			status := "ok"
			if len(missing) > 0 {
				status = "missing: " + strings.Join(missing, ", ")
				bad = true
			}
			extra := ""
			if len(nocheck) > 0 {
				extra = "no check: " + strings.Join(nocheck, ", ")
			}
			fmt.Fprintf(tw, "  %s\t%s\t%s\t%s\n", libName, target, status, extra)
		}
	}
	tw.Flush()
	if bad {
		return 1
	}
	return 0
}
