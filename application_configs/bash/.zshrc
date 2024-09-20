# handle title of ssh window from windows terminal
echo -ne "\033]0;${USER}@$(hostname | cut -d'.' -f1)\007"

if [ -f ~/.bash_aliases ]; then
    echo "sourcing bash_aliases"
    . ~/.bash_aliases
else
    alias myupdater='sh ~/dotfiles/scripts/my_updater.sh'
    alias srcaliases='source ~/.bashrc'
fi

# change prompt to show full path
export PROMPT='%n@%m:%~$ '

# Set PATH for OpenVPN
if [ -x "/usr/local/opt/openvpn/sbin" ]; then
    export PATH="/usr/local/opt/openvpn/sbin:$PATH"
fi

# Set PATH for Homebrew
if [ -x "/opt/homebrew/bin/brew" ]; then
    # For Apple Silicon Macs
    export PATH="/opt/homebrew/bin:$PATH"
fi

# Set PATH for Python 3.10
if [ -x "/opt/homebrew/opt/python@3.10/libexec/bin" ]; then
    export PATH="/opt/homebrew/opt/python@3.10/libexec/bin:$PATH"
fi

# Add ~/.pyenv/shims directory to PATH for pyenv shims
if [ -x "$HOME/.pyenv/shims" ]; then
    export PATH="$HOME/.pyenv/shims:$PATH"
fi
