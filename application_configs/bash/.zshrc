echo "Sourced: ~/.zshrc"

### Terminal Config ###

# History Configuration
export HISTFILE=~/.zsh_history
export HISTSIZE=1000000
export SAVEHIST=1000000

# Set history options
setopt SHARE_HISTORY          # Share history across all sessions (implies APPEND + INC_APPEND)
setopt HIST_IGNORE_DUPS       # Don't record duplicate entries
setopt HIST_IGNORE_ALL_DUPS   # Delete old duplicate entries
setopt HIST_IGNORE_SPACE      # Don't record entries starting with space
setopt HIST_SAVE_NO_DUPS      # Don't write duplicate entries to history file
setopt HIST_REDUCE_BLANKS     # Remove superfluous blanks
setopt HIST_VERIFY            # Show command with history expansion before running
setopt EXTENDED_HISTORY       # Save timestamp and duration

# Force load existing history
if [[ -r "$HISTFILE" ]]; then
    fc -R "$HISTFILE"
fi

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

# Auto-symlink ~/.shared_aliases from the dotfiles repo if not already present,
# then source it for all shared aliases and functions.
if [[ ! -f "$HOME/.shared_aliases" ]]; then
    for _d in "$HOME/GitHub" "$HOME/GitHubWSL" "$HOME/HelloFresh/GDrive/Projects"; do
        if [[ -f "$_d/dotfiles/application_configs/bash/.shared_aliases" ]]; then
            ln -s "$_d/dotfiles/application_configs/bash/.shared_aliases" "$HOME/.shared_aliases"
            break
        fi
    done
    unset _d
fi
[[ -f "$HOME/.shared_aliases" ]] && source "$HOME/.shared_aliases"

alias editaliases='nvim ~/.zshrc'

alias cataliases='cat ~/.zshrc'

alias srcaliases='source ~/.zshrc'

### Functions ###

# syncplex = the media remote CLI/TUI; syncdrive = mirror configured media
# onto a drive (defaults to /Users/jason/Media, pass a path to override).
function syncplex() {
    [ -z "$gitDir" ] && { echo "gitDir is not set" >&2; return 1; }
    uv run --project "$gitDir/Sync_Plex/backends/python" syncplex "$@"
}

function syncdrive() {
    [ -z "$gitDir" ] && { echo "gitDir is not set" >&2; return 1; }
    if [ "$#" -eq 0 ]; then
        uv run --project "$gitDir/Sync_Plex/backends/python" syncplex-drive-sync /Users/jason/Media
    else
        uv run --project "$gitDir/Sync_Plex/backends/python" syncplex-drive-sync "$@"
    fi
}

### Machine-local overrides (not synced) ###

[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
