package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

type Mode int

const (
	ModeCheck Mode = iota
	ModeApply
)

func (m Mode) String() string {
	if m == ModeCheck {
		return "check"
	}
	return "apply"
}

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
	var cmd *exec.Cmd
	if strings.HasSuffix(lib, ".ps1") {
		shell := firstOnPath("pwsh", "powershell")
		script := fmt.Sprintf(". '%s'; %s; exit $LASTEXITCODE", lib, fn)
		cmd = exec.Command(shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
	} else {
		cmd = exec.Command("bash", "-c", `source "$1"; "$2"`, "cmdr", lib, fn)
	}
	return cmd
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

// A runner is one command's execution: the step subprocess currently
// running (so a quit can kill it, children included), whether it was killed,
// and the log file the run is being written to.
type runner struct {
	mu      sync.Mutex
	current *exec.Cmd
	killed  bool
	LogPath string
}

func (r *runner) kill() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.killed = true
	if r.current != nil {
		killProcess(r.current)
	}
}

func (r *runner) setCurrent(cmd *exec.Cmd) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.current = cmd
}

func (r *runner) wasKilled() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.killed
}

// argsEnv hands positional arguments to the steps as CMDR_ARGC and
// CMDR_ARG1..N: one variable per argument, so a path with spaces survives.
func argsEnv(args []string) []string {
	env := []string{fmt.Sprintf("CMDR_ARGC=%d", len(args))}
	for i, a := range args {
		env = append(env, fmt.Sprintf("CMDR_ARG%d=%s", i+1, a))
	}
	return env
}

// openRunLog starts the log every run is written to, under ~/logs/cmdr, so a
// failure noticed later is still inspectable (cmdr logs). A log that cannot
// be opened is reported once and the run goes on without one.
func openRunLog(name string, mode Mode, errw io.Writer) (*os.File, string) {
	dir := logsDir()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		fmt.Fprintf(errw, "cmdr: no run log: %v\n", err)
		return nil, ""
	}
	path := filepath.Join(dir, fmt.Sprintf("%s-%s-%s.log", name, mode, time.Now().Format("20060102-150405")))
	f, err := os.Create(path)
	if err != nil {
		fmt.Fprintf(errw, "cmdr: no run log: %v\n", err)
		return nil, ""
	}
	return f, path
}

// runSteps executes a command's steps in order. Check mode runs <fn>_check
// where one exists, keeps going, and reports drift; apply mode runs <fn> and
// stops at the first failure. stdin may be nil (the TUI) - steps that prompt
// only work from the CLI path. Everything cmdr prints and every non-terminal
// step's output also goes to the run log; a terminal step keeps the real
// screen (a TUI cannot draw into a pipe), so the log only notes it ran.
func runSteps(c Command, mode Mode, out, errw io.Writer, stdin io.Reader, args []string, r *runner) (drift bool, err error) {
	lib := libFor(c.Dir, currentPlatform())
	funcs, err := declaredFuncs(lib)
	if err != nil {
		return false, err
	}
	logf, logPath := openRunLog(c.Name, mode, errw)
	if logf != nil {
		defer logf.Close()
		r.LogPath = logPath
		fmt.Fprintf(logf, "cmdr %s %s %s on %s at %s\n", version, c.Name, mode, shortHostname(), time.Now().Format(time.RFC3339))
	}
	all := out
	if logf != nil {
		all = io.MultiWriter(out, logf)
	}
	self, _ := os.Executable()
	env := append(os.Environ(),
		"CMDR_GIT_DIR="+gitDir(),
		"CMDR_REPO_DIR="+filepath.Dir(c.Dir),
		// So steps can call back into built-ins (e.g. repos ensure --check)
		// without guessing where the binary lives.
		"CMDR_BIN="+self,
		"CMDR_LOG="+logPath,
		// Streaming is the core's whole promise, and Python block-buffers
		// stdout when it's a pipe (the TUI viewport): long-running python
		// steps would look silent until exit. Unbuffer every python child.
		"PYTHONUNBUFFERED=1",
	)
	env = append(env, argsEnv(args)...)
	sty := newStyler(out)
	result := "ok"
	defer func() {
		if logf != nil {
			fmt.Fprintf(logf, "result: %s\n", result)
		}
	}()
	for i, s := range c.Steps {
		if i > 0 {
			fmt.Fprintln(all)
		}
		if bin := missingRequires(s); bin != "" {
			fmt.Fprintln(all, sty.rule(s.Name))
			fmt.Fprintln(all, sty.warn("   skipped: "+bin+" not on PATH"))
			continue
		}
		fn := strings.ToLower(s.Name)
		if !funcs[fn] {
			msg := fmt.Sprintf("step %s is not defined in %s", s.Name, filepath.Base(lib))
			if mode == ModeCheck {
				fmt.Fprintln(all, sty.rule(s.Name))
				fmt.Fprintln(all, sty.warn("   DRIFT: "+msg))
				drift = true
				continue
			}
			result = "failed"
			return drift, fmt.Errorf("%s", msg)
		}
		if mode == ModeCheck {
			if !funcs[fn+"_check"] {
				fmt.Fprintln(all, sty.rule(s.Name))
				fmt.Fprintln(all, sty.dim("   no check implemented, would run on apply"))
				continue
			}
			fn += "_check"
		}
		fmt.Fprintln(all, sty.rule(fn))
		stepOut, stepErr := all, errw
		if s.Terminal {
			stepOut = out
			if logf != nil {
				fmt.Fprintln(logf, "   (terminal step: its output went to the screen)")
			}
		} else if logf != nil {
			stepErr = io.MultiWriter(errw, logf)
		}
		cmd := stepCmd(lib, fn)
		cmd.Stdout, cmd.Stderr, cmd.Stdin = stepOut, stepErr, stdin
		cmd.Env = env
		// Own process group only for a TUI-piped run (no stdin), so a kill
		// reaches the step's children. A step that has the terminal must stay
		// in the foreground group: outside it, the first read of the terminal
		// stops the process (SIGTTIN) and the run just sits there.
		if stdin == nil {
			setProcessGroup(cmd)
		}
		r.setCurrent(cmd)
		runErr := cmd.Run()
		r.setCurrent(nil)
		if r.wasKilled() {
			fmt.Fprintln(all, sty.bad("   KILLED: "+s.Name))
			result = "killed"
			return drift, fmt.Errorf("step %s killed", s.Name)
		}
		if runErr != nil {
			if mode == ModeCheck {
				drift = true
				fmt.Fprintln(all, sty.warn("   ^ drift: "+s.Name+" needs attention"))
				continue
			}
			fmt.Fprintln(all, sty.bad("   FAILED: "+s.Name+" ("+runErr.Error()+")"))
			result = "failed"
			return drift, fmt.Errorf("step %s failed: %w", s.Name, runErr)
		}
		fmt.Fprintln(all, sty.good("   ok: "+s.Name))
	}
	if drift {
		result = "drift"
	}
	return drift, nil
}
