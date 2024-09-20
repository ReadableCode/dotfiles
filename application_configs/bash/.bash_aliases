### Variables ###

if [ -d "$HOME/GitHub/" ]; then
    gitDir="$HOME/GitHub/"
elif [ -d "$HOME/HelloFresh/GDrive/Projects/" ]; then
    gitDir="$HOME/HelloFresh/GDrive/Projects/"
fi
# echo "gitDir is: $gitDir"


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
alias datatoolpack='cd $gitDir/Data_Tool_Pack/'
alias finance='cd $gitDir/na-finops/'
alias hfpulls='bash $gitDir/dotfiles/scripts/git_pull_hf_repos.sh'
alias hfvpncheck='bash $gitDir/dotfiles/scripts/check_hf_vpn.sh'


### Script Shortcuts ###

alias todo='python3 $gitDir/Terminal_To_Do/src/main.py'
alias deploytools='python3 $gitDir/Data_Tool_Pack/src/deploy_tools.py'
alias ourcashprojection='python3 $gitDir/Our_Cash/src/finance_projection.py'
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

