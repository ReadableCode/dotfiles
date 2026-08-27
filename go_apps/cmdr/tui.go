package main

import (
	"bufio"
	"fmt"
	"io"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// The TUI renders the same registry as the CLI and does nothing bespoke per
// command: list, plan, run, stream stdout in a pane. Anything needing rich
// UI is its own TUI and this one just launches it.

type uiState int

const (
	stList uiState = iota
	stDetail
	stConfirm
	stRunning
	stDone
)

type lineMsg string

type doneMsg struct {
	drift bool
	err   error
	mode  Mode
}

type model struct {
	cmds   []Command
	cursor int
	state  uiState
	vp     viewport.Model
	lines  []string
	events chan tea.Msg
	result doneMsg
	width  int
	height int
}

var (
	titleStyle  = lipgloss.NewStyle().Bold(true)
	dimStyle    = lipgloss.NewStyle().Faint(true)
	badStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("1"))
	warnStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	okStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	cursorStyle = lipgloss.NewStyle().Reverse(true)
)

func runTUI() error {
	m := model{
		cmds: discoverCommands(gitDir()),
		vp:   viewport.New(80, 20),
	}
	_, err := tea.NewProgram(m, tea.WithAltScreen()).Run()
	return err
}

func (m model) Init() tea.Cmd { return nil }

func waitEvent(ch chan tea.Msg) tea.Cmd {
	return func() tea.Msg { return <-ch }
}

// startRun executes the selected command in a goroutine, streaming its
// merged output through a pipe into bubbletea messages. The done message is
// sent by the same goroutine that drains the pipe, so it always arrives
// after the last line.
func (m model) startRun(mode Mode) (model, tea.Cmd) {
	m.state = stRunning
	m.lines = nil
	m.vp.SetContent("")
	m.events = make(chan tea.Msg, 64)
	c := m.cmds[m.cursor]
	pr, pw := io.Pipe()
	res := make(chan doneMsg, 1)
	go func() {
		drift, err := runSteps(c, mode, pw, pw, nil)
		pw.Close()
		res <- doneMsg{drift: drift, err: err, mode: mode}
	}()
	events := m.events
	go func() {
		sc := bufio.NewScanner(pr)
		sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
		for sc.Scan() {
			events <- lineMsg(sc.Text())
		}
		events <- <-res
	}()
	return m, waitEvent(m.events)
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.vp.Width = msg.Width
		m.vp.Height = msg.Height - 3
		return m, nil
	case lineMsg:
		m.lines = append(m.lines, string(msg))
		m.vp.SetContent(strings.Join(m.lines, "\n"))
		m.vp.GotoBottom()
		return m, waitEvent(m.events)
	case doneMsg:
		m.result = msg
		m.state = stDone
		return m, nil
	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	if m.state == stRunning || m.state == stDone {
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	switch m.state {
	case stList:
		switch key {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.cmds)-1 {
				m.cursor++
			}
		case "enter":
			if len(m.cmds) > 0 {
				m.state = stDetail
			}
		}
	case stDetail:
		runnable, _ := applicable(m.cmds[m.cursor])
		switch key {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "esc":
			m.state = stList
		case "c":
			if runnable {
				nm, cmd := m.startRun(ModeCheck)
				return nm, cmd
			}
		case "a":
			if runnable {
				m.state = stConfirm
			}
		}
	case stConfirm:
		if key == "y" {
			nm, cmd := m.startRun(ModeApply)
			return nm, cmd
		}
		m.state = stDetail
	case stRunning:
		// Note: quitting here abandons the TUI but the step subprocess keeps
		// running to completion; there is no kill in v0.
		if key == "ctrl+c" {
			return m, tea.Quit
		}
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	case stDone:
		switch key {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "esc", "enter":
			m.state = stList
		default:
			var cmd tea.Cmd
			m.vp, cmd = m.vp.Update(msg)
			return m, cmd
		}
	}
	return m, nil
}

func (m model) View() string {
	var b strings.Builder
	switch m.state {
	case stList:
		b.WriteString(titleStyle.Render("cmdr "+version) +
			dimStyle.Render("  fleet commands on "+shortHostname()) + "\n\n")
		if len(m.cmds) == 0 {
			b.WriteString("no commands discovered (no sibling repos with a commands/ dir)\n")
		}
		for i, c := range m.cmds {
			ok, reason := applicable(c)
			line := fmt.Sprintf("  %-10s %-12s %s", c.Name, "("+c.Source+")", c.Description)
			if !ok {
				line += "  [gated: " + reason + "]"
			}
			if i == m.cursor {
				line = cursorStyle.Render(line)
			} else if !ok {
				line = dimStyle.Render(line)
			}
			b.WriteString(line + "\n")
		}
		b.WriteString("\n" + dimStyle.Render("enter: plan   j/k: move   q: quit"))
	case stDetail, stConfirm:
		c := m.cmds[m.cursor]
		b.WriteString(titleStyle.Render(c.Name) + "  " + dimStyle.Render(c.Description) + "\n\n")
		b.WriteString(dimStyle.Render("lib: "+libFor(c.Dir, currentPlatform())) + "\n")
		for _, s := range c.Steps {
			b.WriteString("  " + s.Name)
			if len(s.Requires) > 0 {
				b.WriteString(dimStyle.Render("  requires " + strings.Join(s.Requires, ", ")))
			}
			b.WriteString("\n")
		}
		if ok, reason := applicable(c); !ok {
			b.WriteString("\n" + badStyle.Render("gated off here: "+reason) + "\n")
			b.WriteString(dimStyle.Render("esc: back   q: quit"))
		} else if m.state == stConfirm {
			b.WriteString("\n" + warnStyle.Render("apply for real? y to confirm, any other key to cancel"))
		} else {
			b.WriteString("\n" + dimStyle.Render("c: check (read-only)   a: apply   esc: back   q: quit"))
		}
	case stRunning, stDone:
		c := m.cmds[m.cursor]
		header := titleStyle.Render(c.Name) + " "
		switch {
		case m.state == stRunning:
			header += warnStyle.Render("running...")
		case m.result.err != nil:
			header += badStyle.Render("FAILED: " + m.result.err.Error())
		case m.result.mode == ModeCheck && m.result.drift:
			header += warnStyle.Render("drift detected")
		case m.result.mode == ModeCheck:
			header += okStyle.Render("no drift")
		default:
			header += okStyle.Render("done")
		}
		b.WriteString(header + "\n")
		b.WriteString(m.vp.View() + "\n")
		if m.state == stDone {
			b.WriteString(dimStyle.Render("enter/esc: back   q: quit"))
		} else {
			b.WriteString(dimStyle.Render("streaming... (scroll with arrows)"))
		}
	}
	return b.String()
}
