### Terminal Config ###

# Detect the type of terminal: WSL, Linux, or macOS
detect_terminal_type() {
	if grep -qEi "(Microsoft|WSL)" /proc/version &>/dev/null; then
		echo "Running in WSL"
		TERMINAL_TYPE="WSL"
	elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
		echo "Running on Linux"
		TERMINAL_TYPE="Linux"
	elif [[ "$OSTYPE" == "darwin"* ]]; then
		echo "Running on macOS"
		TERMINAL_TYPE="macOS"
	else
		echo "Unknown system, skipping pyenv setup"
		TERMINAL_TYPE="Unknown"
	fi
}

detect_terminal_type

# Colors for prompt
RESET="\[\033[0m\]"
BOLD="\[\033[1m\]"
RED="\[\033[31m\]"
GREEN="\[\033[32m\]"
YELLOW="\[\033[33m\]"
BLUE="\[\033[34m\]"
MAGENTA="\[\033[35m\]"
CYAN="\[\033[36m\]"

# Git branch prompt function
git_branch() {
	# Check if we are in a Git repository
	if git rev-parse --is-inside-work-tree &>/dev/null; then
		# Get the current branch name
		local branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
		echo "${YELLOW}(${branch})${RESET}"
	fi
}

# Customize the PS1 prompt with colors
if [[ $TERMINAL_TYPE == "macOS" || $TERMINAL_TYPE == "Linux" || $TERMINAL_TYPE == "WSL" ]]; then
	# Try to include git-prompt.sh if available
	if [[ -f /usr/local/etc/bash_completion.d/git-prompt.sh ]]; then
		source /usr/local/etc/bash_completion.d/git-prompt.sh
		PS1="${BOLD}${GREEN}\u${RESET}@${CYAN}\h${RESET}:${BLUE}\w${RESET}$(__git_ps1 " ${YELLOW}(%s)${RESET}")\$ "
	elif [[ -f /usr/share/git-core/contrib/completion/git-prompt.sh ]]; then
		source /usr/share/git-core/contrib/completion/git-prompt.sh
		PS1="${BOLD}${GREEN}\u${RESET}@${CYAN}\h${RESET}:${BLUE}\w${RESET}$(__git_ps1 " ${YELLOW}(%s)${RESET}")\$ "
	else
		# Fallback to custom git_branch function
		PS1="${BOLD}${GREEN}\u${RESET}@${CYAN}\h${RESET}:${BLUE}\w ${RESET}$(git_branch)\$ "
	fi
else
	# Default prompt if system type is unknown
	PS1="${BOLD}${GREEN}\u${RESET}@${CYAN}\h${RESET}:${BLUE}\w\$ "
fi

# Reload Bash profile if sourced
echo "Terminal configured for $TERMINAL_TYPE"

alias editaliases='nvim ~/.bash_aliases'

alias cataliases='cat ~/.bash_aliases'

alias srcaliases='source ~/.bashrc'

### Paths ###

set_git_dir() {
	if [ -d "$HOME/GitHub/" ]; then
		gitDir="$HOME/GitHub/"
	elif [ -d "$HOME/HelloFresh/GDrive/Projects/" ]; then
		gitDir="$HOME/HelloFresh/GDrive/Projects/"
	else
		echo "No suitable git directory found"
		gitDir=""
	fi
}

set_git_dir

alias myscripts='cd $gitDir/dotfiles/scripts/'
alias linux='cd ~/Documents/Technology/Linux/'
alias githubdir='cd $gitDir'
alias datatoolpack='cd $gitDir/Data_Tool_Pack_Py/'
alias finance='cd $gitDir/na-finops/'

### Python ###

alias venvactivate='source ./.venv/bin/activate'

alias venvdeactivate='deactivate'

function run_python_script() {
	# Check if a file path argument is provided
	if [ -z "$1" ]; then
		echo "Usage: run_python_script <python_script_path>"
		return 1
	fi

	echo "Running Python script: $1"

	# Extract the directory from the provided file path
	script_path="$1"
	script_dir=$(dirname "$script_path")

	# Move up one directory level to check for the .venv folder
	venv_dir="$(dirname "$script_dir")/.venv"

	# Change to the script directory
	echo "Changing to script directory: $script_dir"
	cd "$script_dir" || return

	# Check if the .venv folder exists in the parent directory
	if [ -d "$venv_dir" ]; then
		echo "Project .venv detected at: $venv_dir"

		# Activate the .venv environment
		source "$venv_dir/bin/activate"

		# Run the script using the .venv environment
		python3 "$script_path"

		# Deactivate the environment afterward
		deactivate
		return 0
	else
		echo "No project .venv found in parent directory. Running the script with system Python."
	fi

	# Run the script using the system Python as a fallback
	python3 "$script_path"
}

function deploytools() {
	if [ -z "$gitDir" ]; then
		echo "gitDir is not set"
		return 1
	fi
	run_python_script "$gitDir/Data_Tool_Pack_Py/src/deploy_tools.py"
}

function todo() {
	if [ -z "$gitDir" ]; then
		echo "gitDir is not set"
		return 1
	fi
	run_python_script "$gitDir/Terminal_To_Do/src/main.py"
}

### Command Shortcuts ###

alias ll='ls -AlhF'

function alias_cat_to_bat() {
	if command -v bat &>/dev/null; then
		echo "'bat' is installed. Aliasing 'cat' to 'bat'."
		alias cat='bat'
	elif command -v batcat &>/dev/null; then
		echo "'batcat' is installed. Aliasing 'cat' to 'batcat'."
		alias cat='batcat'
	else
		echo "'bat' or 'batcat' is not installed. No alias created."
	fi
}

alias openbranchdiffs='cd $(git rev-parse --show-toplevel) && git diff --name-only master...HEAD | xargs -I{} code {}'

alias hfpulls='bash $gitDir/na-finops/scripts/git_pull_hf_repos.sh'
alias hfvpncheck='bash $gitDir/na-finops/scripts/check_hf_vpn.sh'

### Script Shortcuts ###

alias myupdater='sh $gitDir/dotfiles/scripts/my_updater.sh'
alias weather='sh $gitDir/dotfiles/scripts/weather.sh'
alias getpubip='sh $gitDir/dotfiles/scripts/get_my_public_ip.sh'

### Program Shortcuts ###

alias speed='speedtest-cli'
alias windirstat='ncdu'
alias mountcheck='mount | grep "sd"'

### Servers ###

alias startcodeserver='code-server serve-local --host 0.0.0.0 --without-connection-token'

function startjupyterlab {
	# Change to the directory defined by gitDir
	cd $gitDir

	# Run the jupyter lab command
	jupyter lab --ip=0.0.0.0 --port=8181
}

### AI Shortcuts ###

function startollama {
	if command -v ollama >/dev/null 2>&1; then
		ollama serve
	else
		echo "ollama is not installed. Install it by running:"
		echo "curl https://ollama.ai/install.sh | sh"
	fi
}

alias pullollamamodels='ollama pull llama2-uncensored'

alias runollama='ollama run llama2-uncensored'

alias stopollama='kill $(pgrep -f "ollama serve")'

### GPU Shortcuts ###

alias gpustatus='watch -n 0.5 nvidia-smi'

### VPN Shortcuts ###

alias vpnhello='openvpn3 session-start --config ~/hellofresh.ovpn'
alias vpnhellov2='sudo openvpn --config ~/hellofresh.ovpn --daemon hellofresh-openvpn'
alias vpnhome='openvpn3 session-start --config ~/asusrouter.ovpn'
alias killvpn='sudo kill $(pgrep openvpn)'

### Google Shortcuts ###

alias unmountgoogle='umount ~/GoogleDrive'
alias mountgoogle='google-drive-ocamlfuse ~/GoogleDrive'

### SSH Shortcuts ###

# Workstations #
alias sshryzenwhite='ssh jason@RyzenWhite'
alias sshspectre='ssh jason@Spectre'
alias sshzephyrus='ssh jason@JasonZephyrus'
alias sshmac='ssh jason@MacbookPro12'

# Upstairs Rack #
alias sshelite='ssh jason@EliteDesk'
alias sshnuk='ssh jason@nukbuntu'
alias sshopti='ssh jason@Optiplex9020'
alias sshpav5='ssh jason@Pavilioni5'

# Servers #
alias sshbehemoth='ssh root@behemoth'

# Appliancs #
alias sshpi4='ssh pi@raspberrypi4'
alias sshpi4a='ssh pi@raspberrypi4a'
alias sshpi3='ssh pi@raspberrypi3'
alias sshpi3a='ssh pi@raspberrypi3a'
alias sshpi0='ssh pi@raspberrypi0'

# Rebeca #
alias sshshelly='ssh rebeca@Shelly'

# HelloFresh #
alias sshhello='ssh jason@192.168.86.4'
alias sshhellowin='ssh HELLOFRESH\\16937827583938060798@HelloFreshWindows'

# GinaMary #
alias sshginamary='ssh gaddy_five@ginagaddysimac'

# Android #
alias sshtabs7p='ssh u0_a1053@GalaxyTabS7P -p 8022'
