### Terminal Config ###

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

alias editaliases='nvim ~/.bash_aliases'

alias cataliases='cat ~/.bash_aliases'

alias srcaliases='source ~/.bashrc'

### Paths ###

alias myscripts='cd $gitDir/dotfiles/scripts/'
alias linux='cd ~/Documents/Technology/Linux/'
alias datatoolpack='cd $gitDir/Data_Tool_Pack_Py/'

# HelloFresh #
alias finance='cd $gitDir/na-finops/'
alias kubelogs='~/HelloFresh/GDrive/Projects/na-finops/scripts/kube_container_follow_logs.sh'
alias kubebash='~/HelloFresh/GDrive/Projects/na-finops/scripts/kube_container_bash.sh'
alias kubedelete='~/HelloFresh/GDrive/Projects/na-finops/scripts/kube_container_delete.sh'

### Program Shortcuts ###

alias windirstat='ncdu'
alias mountcheck='mount | grep "sd"'
alias neofetch='fastfetch'

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

### Kubectl ###

alias k="kubectl"
alias kgp="kubectl get pods -o wide"
alias kgn="kubectl get nodes -o wide"

alias hfvpncheck='bash $gitDir/na-finops/scripts/check_hf_vpn.sh'
