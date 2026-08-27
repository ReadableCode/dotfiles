package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)

type Mode int

const (
	ModeCheck Mode = iota
	ModeApply
)

// libFor returns the platform lib the runner sources. darwin and linux share
// lib.sh (a function body branches internally if it must); windows gets
// lib.ps1.
func libFor(dir, platform string) string {
	if platform == "windows" {
		return filepath.Join(dir, "lib.ps1")
	}
	return filepath.Join(dir, "lib.sh")
}

func firstOnPath(names ...string) string {
	for _, n := range names {
		if _, err := exec.LookPath(n); err == nil {
			return n
		}
	}
	return ""
}

// declaredFuncs asks the shell itself which functions a lib defines
// (declare -F / Get-Command) - this is what makes coverage drift VISIBLE
// (cmdr doctor) instead of silent. Names come back lowercased and every
// lookup lowercases too, because PowerShell names are case-insensitive.
// With no PowerShell on this machine (a mac auditing lib.ps1), it falls back
// to a static scan of the file.
func declaredFuncs(lib string) (map[string]bool, error) {
	funcs := map[string]bool{}
	if strings.HasSuffix(lib, ".ps1") {
		if shell := firstOnPath("pwsh", "powershell"); shell != "" {
			script := fmt.Sprintf(". '%s'; Get-Command -CommandType Function | ForEach-Object Name", lib)
			out, err := exec.Command(shell, "-NoProfile", "-Command", script).Output()
			if err != nil {
				return nil, fmt.Errorf("probing %s: %w", lib, err)
			}
			for _, name := range strings.Fields(string(out)) {
				funcs[strings.ToLower(name)] = true
			}
			return funcs, nil
		}
		data, err := os.ReadFile(lib)
		if err != nil {
			return nil, err
		}
		re := regexp.MustCompile(`(?mi)^\s*function\s+([A-Za-z0-9_-]+)`)
		for _, m := range re.FindAllStringSubmatch(string(data), -1) {
			funcs[strings.ToLower(m[1])] = true
		}
		return funcs, nil
	}
	out, err := exec.Command("bash", "-c", `source "$1" >/dev/null 2>&1; declare -F`, "cmdr", lib).Output()
	if err != nil {
		return nil, fmt.Errorf("probing %s: %w", lib, err)
	}
	for _, line := range strings.Split(string(out), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 3 {
			funcs[strings.ToLower(fields[2])] = true
		}
	}
	return funcs, nil
}

// stepCmd builds the subprocess for one step function: source the lib, call
// the function. The core never knows what the function does.
func stepCmd(lib, fn string) *exec.Cmd {
	if strings.HasSuffix(lib, ".ps1") {
		shell := firstOnPath("pwsh", "powershell")
		script := fmt.Sprintf(". '%s'; %s; exit $LASTEXITCODE", lib, fn)
		return exec.Command(shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
	}
	return exec.Command("bash", "-c", `source "$1"; "$2"`, "cmdr", lib, fn)
}

// --- output decoration ---
// ANSI directly, no lipgloss: this writes into arbitrary io.Writers. ASCII
// rule characters on purpose (same reason as deploy_configs.py): old Windows
// consoles choke on box drawing. Color is on for the TUI pipe and for a real
// terminal, off when piped to a file/grep or NO_COLOR is set.

type styler struct{ on bool }

func newStyler(w io.Writer) styler {
	if os.Getenv("NO_COLOR") != "" {
		return styler{}
	}
	if f, ok := w.(*os.File); ok {
		st, err := f.Stat()
		return styler{on: err == nil && st.Mode()&os.ModeCharDevice != 0}
	}
	return styler{on: true} // io.Pipe into the TUI viewport: color wanted
}

func (s styler) paint(code, text string) string {
	if !s.on {
		return text
	}
	return "\033[" + code + "m" + text + "\033[0m"
}

func (s styler) rule(title string) string {
	line := "-- " + title + " "
	if n := 56 - len(line); n > 0 {
		line += strings.Repeat("-", n)
	}
	return s.paint("1;36", line) // bold cyan, like gitpullall's dividers
}

func (s styler) dim(text string) string  { return s.paint("2", text) }
func (s styler) warn(text string) string { return s.paint("1;33", text) }
func (s styler) good(text string) string { return s.paint("1;32", text) }
func (s styler) bad(text string) string  { return s.paint("1;31", text) }

// missingRequires is a PATH lookup ONLY, by design: some fleet hosts alert
// on every failed sudo, so the core never tests whether it could escalate.
func missingRequires(s Step) string {
	for _, bin := range s.Requires {
		if _, err := exec.LookPath(bin); err != nil {
			return bin
		}
	}
	return ""
}

// runSteps executes a command's steps in order. Check mode runs <fn>_check
// where one exists, keeps going, and reports drift; apply mode runs <fn> and
// stops at the first failure. stdin may be nil (the TUI) - steps that prompt
// (sudo) only work from the CLI path.
func runSteps(c Command, mode Mode, out, errw io.Writer, stdin io.Reader) (drift bool, err error) {
	lib := libFor(c.Dir, currentPlatform())
	funcs, err := declaredFuncs(lib)
	if err != nil {
		return false, err
	}
	self, _ := os.Executable()
	env := append(os.Environ(),
		"CMDR_GIT_DIR="+gitDir(),
		"CMDR_REPO_DIR="+filepath.Dir(c.Dir),
		// So steps can call back into built-ins (e.g. repos ensure --check)
		// without guessing where the binary lives.
		"CMDR_BIN="+self,
	)
	sty := newStyler(out)
	for i, s := range c.Steps {
		if i > 0 {
			fmt.Fprintln(out)
		}
		if bin := missingRequires(s); bin != "" {
			fmt.Fprintln(out, sty.rule(s.Name))
			fmt.Fprintln(out, sty.warn("   skipped: "+bin+" not on PATH"))
			continue
		}
		fn := strings.ToLower(s.Name)
		if !funcs[fn] {
			msg := fmt.Sprintf("step %s is not defined in %s", s.Name, filepath.Base(lib))
			if mode == ModeCheck {
				fmt.Fprintln(out, sty.rule(s.Name))
				fmt.Fprintln(out, sty.warn("   DRIFT: "+msg))
				drift = true
				continue
			}
			return drift, fmt.Errorf("%s", msg)
		}
		if mode == ModeCheck {
			if !funcs[fn+"_check"] {
				fmt.Fprintln(out, sty.rule(s.Name))
				fmt.Fprintln(out, sty.dim("   no check implemented, would run on apply"))
				continue
			}
			fn += "_check"
		}
		fmt.Fprintln(out, sty.rule(fn))
		cmd := stepCmd(lib, fn)
		cmd.Stdout, cmd.Stderr, cmd.Stdin = out, errw, stdin
		cmd.Env = env
		if runErr := cmd.Run(); runErr != nil {
			if mode == ModeCheck {
				drift = true
				fmt.Fprintln(out, sty.warn("   ^ drift: "+s.Name+" needs attention"))
				continue
			}
			fmt.Fprintln(out, sty.bad("   FAILED: "+s.Name+" ("+runErr.Error()+")"))
			return drift, fmt.Errorf("step %s failed: %w", s.Name, runErr)
		}
		fmt.Fprintln(out, sty.good("   ok: "+s.Name))
	}
	return drift, nil
}
