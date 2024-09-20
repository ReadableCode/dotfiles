" For linux this file needs to be symlinked to ~/.config/nvim/
" For windows powershell this file needs to be symlinked to %USERPROFILE%\AppData\Local\nvim\init.vim
"   Open a powershell terminal as an administrator
"   cd $env:USERPROFILE\AppData\Local
"   mkdir nvim
"   cd nvim
"   cmd /c mklink init.vim C:\Users\jason\GitHub\dotfiles\application_configs\nvim\init.vim
"   OR
"   cmd /c mklink init.vim C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\nvim\init.vim

" Install vim-plug for managing Neovim plugins:
" Linux or Mac:
"   You can run this command in your terminal to install vim-plug:
"   curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
" Windows
"   iwr -useb https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim | ni "$(@($env:XDG_DATA_HOME, $env:LOCALAPPDATA)[$null -eq $env:XDG_DATA_HOME])/nvim-data/site/autoload/plug.vim" -Force

" Load the vim-plug plugin manager
" open Neovim and run :PlugInstall to install the plugins

" Specify the plugin manager to begin managing
call plug#begin('~/.config/nvim/plugged')

" Define the plugins you want to install
Plug 'preservim/nerdtree'
Plug 'ThePrimeagen/vim-be-good'
Plug 'tpope/vim-fugitive'

" End of the plugin section
call plug#end()

set relativenumber
let NERDTreeShowHidden=1
set mouse=a

" Use 4 spaces for indentation in Python files
autocmd FileType python setlocal expandtab
autocmd FileType python setlocal shiftwidth=4
autocmd FileType python setlocal softtabstop=4

" Use 2 spaces for indentation in Markdown files
autocmd FileType markdown setlocal expandtab
autocmd FileType markdown setlocal shiftwidth=2
autocmd FileType markdown setlocal softtabstop=2

" Customize the colors for Git diffs
highlight DiffAdd cterm=bold ctermbg=NONE ctermfg=22 gui=bold guibg=NONE guifg=#00FF00
highlight DiffChange cterm=bold ctermbg=NONE ctermfg=208 gui=bold guibg=NONE guifg=#FFA500
highlight DiffDelete cterm=bold ctermbg=NONE ctermfg=52 gui=bold guibg=NONE guifg=#FF0000

" Git diff side by side
command! Gitdiff vertical Gdiffsplit
