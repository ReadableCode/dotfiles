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
"   curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
" Windows
"   iwr -useb https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim | ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force

" If this file throws errors about "Error executing Lua...field 'uv' a nil value"
"   then you need to install the latest version of Neovim using the ppa
" sudo apt remove neovim
" sudo add-apt-repository ppa:neovim-ppa/unstable -y
" sudo apt update
" sudo apt install neovim

" Load the vim-plug plugin manager
" open Neovim and run :PlugInstall to install the plugins

" Then do:
" install node
" For Linux:
"   sudo apt update
"   sudo apt install nodejs npm
" For Windows:
"   winget install OpenJS.NodeJS
"   In Neovim, run :Mason
"   Press i to install pyright if it’s not already installed.
"   Restart your shell to take effect

call plug#begin(stdpath('data') . '/plugged')

" Define the plugins you want to install
Plug 'preservim/nerdtree'
Plug 'ThePrimeagen/vim-be-good'
Plug 'tpope/vim-fugitive'

" Add needed plugins for LSPs
Plug 'neovim/nvim-lspconfig'
Plug 'williamboman/mason.nvim'
Plug 'williamboman/mason-lspconfig.nvim'

" GitHub Copilot inline completions (ghost text, <Tab> to accept)
" Run :Copilot setup once after :PlugInstall to authenticate.
" Requires Node.js >= 20 on PATH.
Plug 'github/copilot.vim'

" GitHub Copilot Chat (sidebar / :CopilotChat commands)
" plenary.nvim is a required dependency.
Plug 'nvim-lua/plenary.nvim'
Plug 'CopilotC-Nvim/CopilotChat.nvim', { 'branch': 'main' }

" End of the plugin section
call plug#end()

" Install for Mason to manage LSPs
" Uses the new vim.lsp.config API (Neovim 0.11+) instead of the deprecated
" require('lspconfig').<server>.setup{} framework. See :help lspconfig-nvim-0.11
lua << EOF
require("mason").setup()
require("mason-lspconfig").setup({
  ensure_installed = { "pyright" },
  -- Do not auto-call the deprecated lspconfig setup handlers
  automatic_enable = false,
})

-- Configure and enable servers using the new built-in API
vim.lsp.config("pyright", {})
vim.lsp.enable("pyright")

-- Copilot Chat setup. See :help CopilotChat or run `:CopilotChat` to open.
require("CopilotChat").setup({
  -- model = "gpt-5",            -- optional; omit to use default
  -- window = { layout = "vertical" },
})
EOF


" -- GitHub Copilot (inline ghost-text completions) ----------------------------
" By default <Tab> accepts the current suggestion. Uncomment the block below
" to remap acceptance to Ctrl-J instead (e.g. if <Tab> conflicts with snippets).
" let g:copilot_no_tab_map = v:true
" imap <silent><script><expr> <C-J> copilot#Accept("\<CR>")
"
" Other built-in insert-mode mappings provided by copilot.vim:
"   <M-]> / <M-[>   next / previous suggestion
"   <C-]>           dismiss suggestion
"   <M-\>           request a suggestion manually

" -- Copilot Chat keymaps ------------------------------------------------------
nnoremap <silent> <Leader>cc :CopilotChat<CR>
xnoremap <silent> <Leader>cc :CopilotChat<CR>
nnoremap <silent> <Leader>ce :CopilotChatExplain<CR>
nnoremap <silent> <Leader>cf :CopilotChatFix<CR>
nnoremap <silent> <Leader>ct :CopilotChatTests<CR>
nnoremap <silent> <Leader>cr :CopilotChatReview<CR>

" Disable copilot.vim's inline ghost text inside the Copilot Chat buffer so it
" doesn't suggest fake "next lines" while you're typing a chat prompt.
autocmd FileType copilot-chat let b:copilot_enabled = v:false

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

" Force Linux line endings (LF) for all files
set fileformats=unix,dos
" Ensure new files always use Unix line endings
autocmd BufNewFile * set fileformat=unix
