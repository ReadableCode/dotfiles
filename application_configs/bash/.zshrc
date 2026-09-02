echo "Sourced: ~/.zshrc"

### Terminal Config ###

# History Configuration
# Keep everything, forever. Deliberately NOT exported: an exported HISTFILE is
# inherited by child shells (bash has no config on macOS) which then write their
# own history into this file.
HISTFILE=~/.zsh_history
HISTSIZE=1000000
SAVEHIST=1000000

# Set history options
setopt APPEND_HISTORY         # Append to the file; never rewrite it wholesale
setopt INC_APPEND_HISTORY     # Write each command as it runs, not at exit
setopt SHARE_HISTORY          # Share history across all running sessions
setopt EXTENDED_HISTORY       # Save timestamp and duration
setopt HIST_IGNORE_SPACE      # Don't record entries starting with space
setopt HIST_REDUCE_BLANKS     # Remove superfluous blanks
setopt HIST_VERIFY            # Show command with history expansion before running
# Never set HIST_IGNORE_ALL_DUPS / HIST_SAVE_NO_DUPS / HIST_IGNORE_DUPS: they
# force a full rewrite of the history file on every write and permanently delete
# the older copy of any repeated command. Duplicates are harmless; keep them.

# zsh's `history` builtin is `fc -l`, which defaults to only the last 16 events
# -- unlike bash, where a bare `history` prints everything. Override it so
# `history` and `history | grep ...` show the whole thing. A function rather
# than an alias so explicit arguments (`history -50`, `history 1 20`) still work.
history() {
    if (( $# )); then
        builtin fc -l "$@"
    else
        builtin fc -l 1
    fi
}

# Aliases for better history viewing
alias hist='fc -l 1'              # Show all history
alias histg='fc -l 1 | grep'      # Search history

# Handle title of SSH window (e.g. Windows Terminal)
echo -ne "\033]0;${USER}@$(hostname | cut -d'.' -f1)\007"

# Advanced prompt with git branch and UV environment support
autoload -Uz vcs_info
setopt prompt_subst

# Configure git info
zstyle ':vcs_info:*' enable git
zstyle ':vcs_info:git:*' formats ' %F{red}(%b)%f'
zstyle ':vcs_info:git:*' actionformats ' %F{red}(%b|%a)%f'

# A venv inherited from a parent process (tmux server, VS Code, launcher)
# sets VIRTUAL_ENV without activate ever running in this shell — detectable
# because the deactivate function only exists in shells that really activated.
if [[ -n "$VIRTUAL_ENV" ]] && ! typeset -f deactivate > /dev/null; then
    path=(${path:#$VIRTUAL_ENV/bin})
    unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT
fi

# Function to get UV environment info
get_uv_env() {
    if [[ -n "$VIRTUAL_ENV" ]]; then
        local env_name=$(basename "$VIRTUAL_ENV")
        if [[ "$env_name" == ".venv" ]]; then
            # For UV projects, show project name instead of .venv
            local project_name=$(basename $(dirname "$VIRTUAL_ENV"))
            echo "%F{green}(uv:$project_name)%f "
        else
            echo "%F{green}($env_name)%f "
        fi
    elif [[ -f "pyproject.toml" && -d ".venv" ]]; then
        # UV project detected but not activated
        local project_name=$(basename "$PWD")
        echo "%F{yellow}(uv:$project_name-inactive)%f "
    fi
}

# Function to check if directory is writable
get_dir_status() {
    if [[ ! -w "$PWD" ]]; then
        echo "%F{red}🔒%f"
    fi
}

# Precmd function to update vcs_info
precmd() {
    vcs_info
}

# Set the prompt
PROMPT='%F{cyan}%n@%m%f:%F{blue}%~%f$(get_uv_env)$(get_dir_status)${vcs_info_msg_0_}
%F{white}$%f '

### Paths ###

# Enable better tab completion
# Homebrew must come first so its completions are in fpath before compinit
if [ -x "/opt/homebrew/bin/brew" ]; then
    export PATH="/opt/homebrew/bin:$PATH"
    fpath=(/opt/homebrew/share/zsh/site-functions $fpath)
    # Casks are downloaded by brew itself, not a browser, so the quarantine flag
    # buys nothing and costs a Gatekeeper "could not verify" dialog on every
    # upgrade of a binary cask (claude-code being the recurring offender).
    export HOMEBREW_CASK_OPTS="--no-quarantine"
fi

# Enable better tab completion
autoload -Uz compinit
compinit

# Case insensitive completion
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

# Menu-style completion
zstyle ':completion:*' menu select

# Completion styling
zstyle ':completion:*:descriptions' format '%U%B%d%b%u'
zstyle ':completion:*:warnings' format '%BSorry, no matches for: %d%b'

# Group matches and describe
zstyle ':completion:*' group-name ''
zstyle ':completion:*:*:-command-:*:*' group-order alias builtins functions commands


### Shared Aliases ###

# Both this file and ~/.shared_aliases are deployed by the same deploy_configs.py
# run, so if this file is here that one is too.
[[ -f "$HOME/.shared_aliases" ]] && source "$HOME/.shared_aliases"

alias editaliases='nvim ~/.zshrc'

alias srcaliases='source ~/.zshrc'

### Functions ###

# The media remote CLI/TUI (Sync_Plex).
function syncplex() {
    [ -z "$gitDir" ] && { echo "gitDir is not set" >&2; return 1; }
    uv run --project "$gitDir/Sync_Plex/backends/python" syncplex "$@"
}

# Mirror configured media onto a drive (defaults to /Users/jason/Media; pass a path to override).
function syncdrive() {
    [ -z "$gitDir" ] && { echo "gitDir is not set" >&2; return 1; }
    if [ "$#" -eq 0 ]; then
        uv run --project "$gitDir/Sync_Plex/backends/python" syncplex-drive-sync /Users/jason/Media
    else
        uv run --project "$gitDir/Sync_Plex/backends/python" syncplex-drive-sync "$@"
    fi
}

# Every VS Code extension update drops a fresh, quarantined copy of the Claude
# Code native binary at
# ~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude,
# and Gatekeeper then blocks it with "claude Not Opened / Apple could not
# verify". HOMEBREW_CASK_OPTS above keeps future brew upgrades clean; nothing
# can pre-empt the extension copies, so run this when the dialog reappears.
function claude-dequarantine() {
    setopt localoptions nullglob
    local f
    local -i found=0 stripped=0
    for f in "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude \
             /opt/homebrew/Caskroom/claude-code/*/claude; do
        [[ -f "$f" ]] || continue
        (( found++ ))
        if ! xattr -p com.apple.quarantine "$f" >/dev/null 2>&1; then
            echo "already clean:  $f"
        elif xattr -d com.apple.quarantine "$f" 2>/dev/null; then
            echo "dequarantined:  $f"
            (( stripped++ ))
        else
            echo "FAILED:         $f" >&2
        fi
    done
    if (( found == 0 )); then
        echo "claude-dequarantine: no claude binaries found" >&2
        return 1
    fi
    echo "claude-dequarantine: stripped $stripped of $found binaries"
}

### Machine-local overrides (not synced) ###

[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
