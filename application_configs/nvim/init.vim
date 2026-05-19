" Neovim configuration (LEGACY)
" The canonical config is now ../nvim/init.lua. This file is kept for
" reference. Neovim loads init.lua before init.vim when both exist.
" See docs/setup_neovim.md for installation and setup instructions.

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
