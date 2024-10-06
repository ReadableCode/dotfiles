### Detect Paths ###

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

### Terminal Type ###

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


### Pyenv Setup ###


# Initialize pyenv based on the terminal type
setup_pyenv() {
	export PYENV_ROOT="$HOME/.pyenv"

    if [[ "$TERMINAL_TYPE" == "WSL" ]]; then
        echo "Checking if pyenv is installed in WSL"
        
        if [ -d "$PYENV_ROOT" ] && [ -x "$PYENV_ROOT/bin/pyenv" ]; then
            echo "Pyenv is installed, setting up pyenv for WSL"
            
            BIN_OLD="/mnt/c/Users/$USER/.pyenv/pyenv-win/bin"
            BIN_NEW="$PYENV_ROOT/bin"
            SHIMS_OLD="/mnt/c/Users/$USER/.pyenv/pyenv-win/shims"
            SHIMS_NEW="$PYENV_ROOT/shims"

            # Replace the Windows pyenv-win paths with the Linux pyenv paths
            export PATH=$(echo $PATH | sed "s@$BIN_OLD@$BIN_NEW@" | sed "s@$SHIMS_OLD@$SHIMS_NEW@")

            # Initialize pyenv for WSL
            eval "$(pyenv init -)"
        else
            echo "Pyenv is not installed in WSL, skipping pyenv setup"
        fi

    elif [[ "$TERMINAL_TYPE" == "Linux" || "$TERMINAL_TYPE" == "macOS" ]]; then
        echo "Checking if pyenv is installed on $TERMINAL_TYPE"

        if command -v pyenv &> /dev/null; then
            echo "Pyenv is installed, setting up pyenv for $TERMINAL_TYPE"

            export PATH="$PYENV_ROOT/bin:$PATH"
            eval "$(pyenv init --path)"
            eval "$(pyenv init -)"
        else
            echo "Pyenv is not installed on $TERMINAL_TYPE, skipping pyenv setup"
        fi
    else
        echo "No pyenv setup for unknown system"
    fi
}


### Functions ###

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

	# Change to the script directory
	echo "Changing to script directory: $script_dir"
	cd "$script_dir" || return

	# Check if the Pipenv environment is installed
	if command -v pipenv >/dev/null 2>&1; then
		pipenv_venv=$(pipenv --venv 2>/dev/null)

		if [ -n "$pipenv_venv" ]; then
			echo "Pipenv environment detected at: $pipenv_venv"

			# Activate the Pipenv environment explicitly
			source "$pipenv_venv/bin/activate"

			# Run the script using the Pipenv environment
			python3 "$script_path"

			# Deactivate the environment afterward
			deactivate
			return 0
		else
			echo "No active Pipenv environment found, attempting to run with system Python."
		fi
	else
		echo "Pipenv is not installed. Running the script with system Python."
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

function ourcashprojection() {
	if [ -z "$gitDir" ]; then
		echo "gitDir is not set"
		return 1
	fi
	run_python_script "$gitDir/Our_Cash/src/finance_projection.py"
}


### Run Functions ###

# Call the git directory detection function
set_git_dir

# Call the detection function
detect_terminal_type

# Call the pyenv setup function
setup_pyenv


### Command Shortcuts ###

alias ll='ls -AlhF'

### Aliases ###

alias editaliases='nvim ~/.bash_aliases'
alias cataliases='cat ~/.bash_aliases'
alias srcaliases='source ~/.bashrc'

### Directory Shortcuts ###

alias myscripts='cd $gitDir/dotfiles/scripts/'
alias linux='cd ~/Documents/Technology/Linux/'
alias githubdir='cd $gitDir'
alias datatoolpack='cd $gitDir/Data_Tool_Pack_Py/'
alias finance='cd $gitDir/na-finops/'
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

### Python Shortcuts ###

alias pipenvactivate='source $(pipenv --venv)/bin/activate'
alias pipenvdeactivate='deactivate'

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

# Power Order Linux #
alias ssh1='ssh pi@raspberrypi0'
alias ssh2='ssh pi@raspberrypi3'
alias ssh3='ssh pi@raspberrypi3a'
alias ssh4='ssh pi@raspberrypi4a'
alias ssh5='ssh pi@raspberrypi4'
alias ssh6='ssh jason@EliteDesk'
alias ssh7='ssh jason@nukbuntu'
alias ssh8='ssh Pavilioni5'
alias ssh9='ssh Optiplex9020'
alias ssh10='ssh jason@MacbookPro12'
alias ssh11='ssh HelloFreshJason'

# Android #
alias sshtabs7p='ssh u0_a1053@GalaxyTabS7P -p 8022'
