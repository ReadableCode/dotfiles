package main

import "github.com/charmbracelet/lipgloss"

// The readablecode "terminal navy" design system (ReadableCode/style-terminal-navy,
// STYLE.md is the source of truth; readable_utils.design_tokens carries the
// same values for the Python TUIs). Hex on purpose: a terminal's 16-colour
// palette is whatever the user's profile says, and the old "24" header was
// a random deep blue on most of them.
const (
	tokenBG          = "#0d1420"
	tokenSurface     = "#121b2a"
	tokenSurface2    = "#182333"
	tokenHairline    = "#273141" // --border flattened onto --surface
	tokenInk         = "#dbe4f0"
	tokenInk2        = "#9fb0c3"
	tokenMuted       = "#7d8b9e"
	tokenGreen       = "#2ea043"
	tokenGreenBright = "#56d364"
	tokenAmberBright = "#e3b341"
	tokenRed         = "#f87171"
	tokenCursor      = "#194529" // --green at 35% over --bg: the selected row
)

var (
	headerStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(tokenInk)).Background(lipgloss.Color(tokenSurface2))
	promptStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(tokenGreenBright)).Background(lipgloss.Color(tokenSurface2))
	colHdrStyle = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenMuted)).Underline(true)
	zebraStyle  = lipgloss.NewStyle().Background(lipgloss.Color(tokenSurface))
	cursorStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(tokenInk)).Background(lipgloss.Color(tokenCursor))
	dimStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenMuted))
	badStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenRed))
	warnStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenAmberBright))
	okStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenGreenBright))
	keyStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(tokenGreenBright)).Background(lipgloss.Color(tokenSurface2))
	labelStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color(tokenInk2)).Background(lipgloss.Color(tokenSurface))
	footerPad   = lipgloss.NewStyle().Background(lipgloss.Color(tokenSurface))
)
