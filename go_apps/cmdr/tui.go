package main

import (
	"bufio"
	"io"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// The TUI renders the same registry as the CLI and does nothing bespoke per
// command. Chrome is modeled on Cash_Flow_Commander's Textual app: header
// bar, zebra-striped table with a row cursor, clickable footer chips.
// Deliberately FLAT: clicking a row (or enter) runs the command immediately,
// c runs its read-only check - no detail screen, no confirm modal. The CLI
// path keeps plan-and-ask for anyone who wants to look before leaping.

type uiState int

const (
	stList uiState = iota
	stRunning
	stDone
)

type lineMsg string

type doneMsg struct {
	drift bool
	err   error
	mode  Mode
}

type binding struct {
	key    string
	label  string
	action string
}

type span struct {
	start, end int
	action     string
}

type model struct {
	cmds      []Command
	cursor    int // index into visible()
	offset    int // first visible row shown
	state     uiState
	filter    string
	filtering bool
	vp        viewport.Model
	lines     []string
	events    chan tea.Msg
	result    doneMsg
	running   *Command
	width     int
	height    int
}

var (
	headerStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("15")).Background(lipgloss.Color("24"))
	colHdrStyle = lipgloss.NewStyle().Faint(true).Underline(true)
	zebraStyle  = lipgloss.NewStyle().Background(lipgloss.Color("235"))
	cursorStyle = lipgloss.NewStyle().Reverse(true)
	dimStyle    = lipgloss.NewStyle().Faint(true)
	badStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("1"))
	warnStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	okStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	keyStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("15")).Background(lipgloss.Color("238"))
	labelStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("250")).Background(lipgloss.Color("236"))
	footerPad   = lipgloss.NewStyle().Background(lipgloss.Color("236"))
)

func runTUI() error {
	m := model{
		cmds: discoverCommands(gitDir()),
		vp:   viewport.New(80, 20),
	}
	_, err := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion()).Run()
	return err
}

func (m model) Init() tea.Cmd { return nil }

// --- bindings and footer (Textual Footer look: clickable chips) ---

func (m model) bindings() []binding {
	switch m.state {
	case stList:
		if m.filtering {
			return []binding{
				{"enter", "Accept", "unfilter"},
				{"escape", "Clear", "clearfilter"},
			}
		}
		return []binding{
			{"enter", "Run", "run"},
			{"c", "Check", "check"},
			{"r", "Refresh", "refresh"},
			{"/", "Filter", "filter"},
			{"q", "Quit", "quit"},
		}
	case stRunning:
		return []binding{{"ctrl+c", "Quit", "quit"}}
	default: // stDone
		if m.result.mode == ModeCheck {
			// A check is a dry run of exactly this command: offer the real
			// run right here instead of a round-trip through the list.
			return []binding{
				{"enter", "Run now", "apply-now"},
				{"escape", "Back", "back"},
				{"q", "Quit", "quit"},
			}
		}
		return []binding{
			{"escape", "Back", "back"},
			{"q", "Quit", "quit"},
		}
	}
}

func footerSpans(items []binding) []span {
	var spans []span
	x := 0
	for _, b := range items {
		w := len(b.key) + len(b.label) + 3 // " key label "
		spans = append(spans, span{start: x, end: x + w, action: b.action})
		x += w
	}
	return spans
}

func (m model) footerView() string {
	var b strings.Builder
	used := 0
	for _, it := range m.bindings() {
		b.WriteString(keyStyle.Render(" " + it.key + " "))
		b.WriteString(labelStyle.Render(it.label + " "))
		used += len(it.key) + len(it.label) + 3
	}
	if pad := m.width - used; pad > 0 {
		b.WriteString(footerPad.Render(strings.Repeat(" ", pad)))
	}
	return b.String()
}

// --- filtering / visible rows ---

func (m model) visible() []Command {
	if m.filter == "" {
		return m.cmds
	}
	f := strings.ToLower(m.filter)
	var out []Command
	for _, c := range m.cmds {
		if strings.Contains(strings.ToLower(c.Name), f) ||
			strings.Contains(strings.ToLower(c.Description), f) {
			out = append(out, c)
		}
	}
	return out
}

func (m model) rowsTop() int {
	if m.filtering || m.filter != "" {
		return 4 // header, blank, filter line, column header
	}
	return 3 // header, blank, column header
}

func (m model) maxRows() int {
	n := m.height - m.rowsTop() - 2 // blank + footer
	if n < 1 {
		n = 1
	}
	return n
}

func (m *model) clampCursor() {
	vis := len(m.visible())
	if m.cursor >= vis {
		m.cursor = vis - 1
	}
	if m.cursor < 0 {
		m.cursor = 0
	}
	if m.cursor < m.offset {
		m.offset = m.cursor
	}
	if m.cursor >= m.offset+m.maxRows() {
		m.offset = m.cursor - m.maxRows() + 1
	}
}

func (m model) selected() *Command {
	vis := m.visible()
	if len(vis) == 0 || m.cursor >= len(vis) {
		return nil
	}
	return &vis[m.cursor]
}

// --- running ---

// startRun executes the selected command in a goroutine, streaming its
// merged output through a pipe into bubbletea messages. The done message is
// sent by the same goroutine that drains the pipe, so it always arrives
// after the last line.
func (m model) startRun(c *Command, mode Mode) (model, tea.Cmd) {
	if c == nil {
		return m, nil
	}
	if ok, _ := applicable(*c); !ok {
		return m, nil
	}
	m.running = c
	m.state = stRunning
	m.lines = nil
	m.vp.Width = m.width
	m.vp.Height = m.height - 3
	m.vp.SetContent("")
	m.events = make(chan tea.Msg, 64)
	pr, pw := io.Pipe()
	res := make(chan doneMsg, 1)
	cmd := *c
	go func() {
		drift, err := runSteps(cmd, mode, pw, pw, nil)
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

func waitEvent(ch chan tea.Msg) tea.Cmd {
	return func() tea.Msg { return <-ch }
}

// --- update ---

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.vp.Width = msg.Width
		m.vp.Height = msg.Height - 3
		m.clampCursor()
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
	case tea.MouseMsg:
		return m.handleMouse(msg)
	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	return m, nil
}

func (m model) act(action string) (tea.Model, tea.Cmd) {
	switch action {
	case "quit":
		return m, tea.Quit
	case "run":
		nm, cmd := m.startRun(m.selected(), ModeApply)
		return nm, cmd
	case "check":
		nm, cmd := m.startRun(m.selected(), ModeCheck)
		return nm, cmd
	case "apply-now": // from the done screen: apply what was just checked
		nm, cmd := m.startRun(m.running, ModeApply)
		return nm, cmd
	case "back":
		m.state = stList
	case "refresh":
		m.cmds = discoverCommands(gitDir())
		m.clampCursor()
	case "filter":
		m.filtering = true
	case "unfilter":
		m.filtering = false
	case "clearfilter":
		m.filter = ""
		m.filtering = false
		m.clampCursor()
	}
	return m, nil
}

func (m model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	if key == "ctrl+c" {
		// Note: quitting mid-run abandons the TUI but the step subprocess
		// keeps running to completion; there is no kill in v0.
		return m, tea.Quit
	}
	if m.state == stList && m.filtering {
		switch msg.Type {
		case tea.KeyEnter:
			return m.act("unfilter")
		case tea.KeyEscape:
			return m.act("clearfilter")
		case tea.KeyBackspace:
			if len(m.filter) > 0 {
				m.filter = m.filter[:len(m.filter)-1]
			}
			m.clampCursor()
			return m, nil
		case tea.KeyRunes, tea.KeySpace:
			m.filter += string(msg.Runes)
			m.clampCursor()
			return m, nil
		}
		return m, nil
	}
	switch m.state {
	case stList:
		switch key {
		case "up", "k":
			m.cursor--
			m.clampCursor()
		case "down", "j":
			m.cursor++
			m.clampCursor()
		case "enter":
			return m.act("run")
		case "c":
			return m.act("check")
		case "r":
			return m.act("refresh")
		case "/":
			return m.act("filter")
		case "q":
			return m.act("quit")
		}
	case stRunning:
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	case stDone:
		switch key {
		case "enter":
			if m.result.mode == ModeCheck {
				return m.act("apply-now")
			}
			return m.act("back")
		case "esc":
			return m.act("back")
		case "q":
			return m.act("quit")
		default:
			var cmd tea.Cmd
			m.vp, cmd = m.vp.Update(msg)
			return m, cmd
		}
	}
	return m, nil
}

func (m model) handleMouse(msg tea.MouseMsg) (tea.Model, tea.Cmd) {
	// Wheel scrolls whatever the screen shows.
	if msg.Button == tea.MouseButtonWheelUp || msg.Button == tea.MouseButtonWheelDown {
		switch m.state {
		case stList:
			if msg.Button == tea.MouseButtonWheelUp {
				m.cursor--
			} else {
				m.cursor++
			}
			m.clampCursor()
			return m, nil
		case stRunning, stDone:
			var cmd tea.Cmd
			m.vp, cmd = m.vp.Update(msg)
			return m, cmd
		}
		return m, nil
	}
	if msg.Action != tea.MouseActionPress || msg.Button != tea.MouseButtonLeft {
		return m, nil
	}
	// Footer chips are clickable on every screen.
	if msg.Y == m.height-1 {
		for _, s := range footerSpans(m.bindings()) {
			if msg.X >= s.start && msg.X < s.end {
				return m.act(s.action)
			}
		}
		return m, nil
	}
	// Clicking a row runs it. That is the whole interaction.
	if m.state == stList {
		row := msg.Y - m.rowsTop()
		if row < 0 {
			return m, nil
		}
		idx := m.offset + row
		if idx >= len(m.visible()) {
			return m, nil
		}
		m.cursor = idx
		m.clampCursor()
		return m.act("run")
	}
	return m, nil
}

// --- view ---

func clip(s string, w int) string {
	if w <= 0 {
		return ""
	}
	r := []rune(s)
	if len(r) <= w {
		return s
	}
	if w == 1 {
		return string(r[:1])
	}
	return string(r[:w-1]) + "…"
}

func pad(s string, w int) string {
	s = clip(s, w)
	if n := w - len([]rune(s)); n > 0 {
		s += strings.Repeat(" ", n)
	}
	return s
}

func (m model) headerView(subtitle string) string {
	left := " cmdr " + version + "  " + subtitle
	right := shortHostname() + " "
	gap := m.width - len([]rune(left)) - len([]rune(right))
	if gap < 1 {
		gap = 1
	}
	return headerStyle.Render(pad(left+strings.Repeat(" ", gap)+right, m.width))
}

func (m model) View() string {
	if m.width == 0 {
		return ""
	}
	var b strings.Builder
	switch m.state {
	case stList:
		b.WriteString(m.headerView("click to run, c to check") + "\n\n")
		if m.filtering || m.filter != "" {
			line := " Filter: " + m.filter
			if m.filtering {
				line += "▏"
			}
			b.WriteString(line + "\n")
		}
		nameW, srcW, statW := 14, 14, 26
		b.WriteString(colHdrStyle.Render(pad(" COMMAND", nameW)+pad(" SOURCE", srcW)+pad(" STATUS", statW)+" DESCRIPTION") + "\n")
		vis := m.visible()
		if len(vis) == 0 {
			b.WriteString(dimStyle.Render("  no commands discovered (no sibling repos with a commands/ dir)") + "\n")
		}
		end := m.offset + m.maxRows()
		if end > len(vis) {
			end = len(vis)
		}
		for i := m.offset; i < end; i++ {
			c := vis[i]
			ok, reason := applicable(c)
			status := "ok"
			if !ok {
				status = "gated: " + reason
			}
			descW := m.width - nameW - srcW - statW - 1
			row := pad(" "+c.Name, nameW) + pad(" "+c.Source, srcW) + pad(" "+status, statW) + pad(" "+c.Description, descW)
			switch {
			case i == m.cursor:
				row = cursorStyle.Render(row)
			case !ok:
				row = dimStyle.Render(row)
			case i%2 == 1:
				row = zebraStyle.Render(row)
			}
			b.WriteString(row + "\n")
		}
		for i := end - m.offset; i < m.maxRows(); i++ {
			b.WriteString("\n")
		}
	case stRunning, stDone:
		c := m.running
		status := warnStyle.Render("running…")
		if m.state == stDone {
			switch {
			case m.result.err != nil:
				status = badStyle.Render("FAILED: " + m.result.err.Error())
			case m.result.mode == ModeCheck && m.result.drift:
				status = warnStyle.Render("drift detected")
			case m.result.mode == ModeCheck:
				status = okStyle.Render("no drift")
			default:
				status = okStyle.Render("done")
			}
		}
		b.WriteString(m.headerView(c.Name) + "\n")
		b.WriteString(" " + status + "\n")
		b.WriteString(m.vp.View() + "\n")
	}
	b.WriteString(m.footerView())
	return b.String()
}
