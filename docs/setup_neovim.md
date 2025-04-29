" For linux this file needs to be symlinked to ~/.config/nvim/
" For windows powershell this file needs to be symlinked to %USERPROFILE%\AppData\Local\nvim\init.vim
"   Open a powershell terminal as an administrator
"   cd $env:USERPROFILE\AppData\Local
"   mkdir nvim
"   cd nvim
"   cmd /c mklink C:\Users\jason\AppData\Local\nvim\init.vim C:\Users\jason\GitHub\dotfiles\application_configs\nvim\init.vim
"   OR
"   cmd /c mklink init.vim C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\nvim\init.vim

" Install vim-plug for managing Neovim plugins:
" Linux or Mac:
"   You can run this command in your terminal to install vim-plug:
"   curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs <https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim>
" Windows
"   iwr -useb <https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim> | ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force

" Load the vim-plug plugin manager
" open Neovim and run :PlugInstall to install the plugins

" Then do:
" on windows will need to install node
" winget install OpenJS.NodeJS
" In Neovim, run :Mason
" Press i to install pyright if it’s not already installed.
" Restart your shell to take effect
