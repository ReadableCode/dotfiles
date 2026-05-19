-- Neovim configuration (Lua)
-- See docs/setup_neovim.md for installation and setup instructions.
-- This file is the canonical config. The legacy init.vim is kept for reference
-- only; Neovim loads init.lua first when both exist.

-- ---------------------------------------------------------------------------
-- Plugins (managed by vim-plug)
-- ---------------------------------------------------------------------------
local Plug = vim.fn['plug#']

vim.call('plug#begin', vim.fn.stdpath('data') .. '/plugged')

Plug('preservim/nerdtree')
Plug('ThePrimeagen/vim-be-good')
Plug('tpope/vim-fugitive')

-- LSPs
Plug('neovim/nvim-lspconfig')
Plug('williamboman/mason.nvim')
Plug('williamboman/mason-lspconfig.nvim')

-- GitHub Copilot inline completions (ghost text, <Tab> to accept)
-- Run :Copilot setup once after :PlugInstall to authenticate.
-- Requires Node.js >= 20 on PATH.
Plug('github/copilot.vim')

-- GitHub Copilot Chat (sidebar / :CopilotChat commands)
-- plenary.nvim is a required dependency (also reused by telescope).
Plug('nvim-lua/plenary.nvim')
Plug('CopilotC-Nvim/CopilotChat.nvim', { branch = 'main' })

-- Treesitter: better syntax highlighting, indent, folds, text objects.
-- Pinned to master; parsers auto-install via the setup() block below.
Plug('nvim-treesitter/nvim-treesitter', { branch = 'master', ['do'] = ':TSUpdate' })

-- Telescope: fuzzy finder for files, grep, buffers, help, LSP symbols, etc.
Plug('nvim-telescope/telescope.nvim', { branch = '0.1.x' })

vim.call('plug#end')

-- ---------------------------------------------------------------------------
-- Auto-install missing plugins on first launch.
-- If any plugin listed above isn't on disk yet, run :PlugInstall once and
-- then source this file again so the require() calls below succeed.
-- ---------------------------------------------------------------------------
local function any_plug_missing()
  for _, plug in pairs(vim.g.plugs or {}) do
    if vim.fn.isdirectory(plug.dir) == 0 then
      return true
    end
  end
  return false
end

if any_plug_missing() then
  vim.api.nvim_create_autocmd('VimEnter', {
    once = true,
    callback = function()
      vim.cmd('PlugInstall --sync')
      vim.cmd('source ' .. vim.fn.stdpath('config') .. '/init.lua')
    end,
  })
end

-- ---------------------------------------------------------------------------
-- Mason + LSP setup
-- Uses the new vim.lsp.config API (Neovim 0.11+) instead of the deprecated
-- require('lspconfig').<server>.setup{} framework. See :help lspconfig-nvim-0.11
-- ---------------------------------------------------------------------------
local ok_mason, mason = pcall(require, 'mason')
if ok_mason then
  mason.setup()
end

local ok_mlsp, mason_lspconfig = pcall(require, 'mason-lspconfig')
if ok_mlsp then
  mason_lspconfig.setup({
    ensure_installed = { 'pyright' },
    -- Do not auto-call the deprecated lspconfig setup handlers
    automatic_enable = false,
  })
end

-- Configure and enable servers using the new built-in API
if vim.lsp.config then
  vim.lsp.config('pyright', {})
  vim.lsp.enable('pyright')
end

-- ---------------------------------------------------------------------------
-- Copilot Chat
-- ---------------------------------------------------------------------------
local ok_chat, copilot_chat = pcall(require, 'CopilotChat')
if ok_chat then
  copilot_chat.setup({
    -- model = 'gpt-5',            -- optional; omit to use default
    -- window = { layout = 'vertical' },
  })
end

-- ---------------------------------------------------------------------------
-- Treesitter
-- Parsers listed in ensure_installed are downloaded & compiled on first use.
-- Add more languages by extending the list, then restart nvim or run :TSUpdate.
-- ---------------------------------------------------------------------------
local ok_ts, ts_configs = pcall(require, 'nvim-treesitter.configs')
if ok_ts then
  ts_configs.setup({
    ensure_installed = {
      'bash', 'json', 'lua', 'markdown', 'markdown_inline',
      'python', 'toml', 'vim', 'vimdoc', 'yaml',
    },
    auto_install = true,
    highlight = { enable = true },
    indent = { enable = true },
  })
end

-- ---------------------------------------------------------------------------
-- Telescope (fuzzy finder)
-- ---------------------------------------------------------------------------
local ok_tele, telescope = pcall(require, 'telescope')
if ok_tele then
  telescope.setup({})
end

-- ---------------------------------------------------------------------------
-- GitHub Copilot (inline ghost-text completions)
-- ---------------------------------------------------------------------------
-- By default <Tab> accepts the current suggestion. Uncomment the block below
-- to remap acceptance to Ctrl-J instead (e.g. if <Tab> conflicts with snippets).
-- vim.g.copilot_no_tab_map = true
-- vim.keymap.set('i', '<C-J>', 'copilot#Accept("\\<CR>")', {
--   silent = true, script = true, expr = true, replace_keycodes = false,
-- })
--
-- Other built-in insert-mode mappings provided by copilot.vim:
--   <M-]> / <M-[>   next / previous suggestion
--   <C-]>           dismiss suggestion
--   <M-\>           request a suggestion manually

-- ---------------------------------------------------------------------------
-- Copilot Chat keymaps
-- ---------------------------------------------------------------------------
local map_opts = { silent = true }
vim.keymap.set('n', '<Leader>cc', ':CopilotChat<CR>',        map_opts)
vim.keymap.set('x', '<Leader>cc', ':CopilotChat<CR>',        map_opts)
vim.keymap.set('n', '<Leader>ce', ':CopilotChatExplain<CR>', map_opts)
vim.keymap.set('n', '<Leader>cf', ':CopilotChatFix<CR>',     map_opts)
vim.keymap.set('n', '<Leader>ct', ':CopilotChatTests<CR>',   map_opts)
vim.keymap.set('n', '<Leader>cr', ':CopilotChatReview<CR>',  map_opts)

-- ---------------------------------------------------------------------------
-- Telescope keymaps  (<Leader>f* = find)
-- ---------------------------------------------------------------------------
vim.keymap.set('n', '<Leader>ff', ':Telescope find_files<CR>', map_opts)
vim.keymap.set('n', '<Leader>fg', ':Telescope live_grep<CR>',  map_opts)
vim.keymap.set('n', '<Leader>fb', ':Telescope buffers<CR>',    map_opts)
vim.keymap.set('n', '<Leader>fh', ':Telescope help_tags<CR>',  map_opts)
vim.keymap.set('n', '<Leader>fr', ':Telescope resume<CR>',     map_opts)

-- ---------------------------------------------------------------------------
-- General editor options
-- ---------------------------------------------------------------------------
vim.opt.relativenumber = true
vim.g.NERDTreeShowHidden = 1
vim.opt.mouse = 'a'

-- Force LF line endings; prefer unix but accept dos
vim.opt.fileformats = { 'unix', 'dos' }

-- ---------------------------------------------------------------------------
-- Autocommands
-- ---------------------------------------------------------------------------
local aug = vim.api.nvim_create_augroup('JasonInit', { clear = true })

-- Disable copilot.vim's inline ghost text inside the Copilot Chat buffer so it
-- doesn't suggest fake "next lines" while you're typing a chat prompt.
vim.api.nvim_create_autocmd('FileType', {
  group = aug,
  pattern = 'copilot-chat',
  callback = function()
    vim.b.copilot_enabled = false
  end,
})

-- Use 4 spaces for indentation in Python files
vim.api.nvim_create_autocmd('FileType', {
  group = aug,
  pattern = 'python',
  callback = function()
    vim.opt_local.expandtab = true
    vim.opt_local.shiftwidth = 4
    vim.opt_local.softtabstop = 4
  end,
})

-- Use 2 spaces for indentation in Markdown files
vim.api.nvim_create_autocmd('FileType', {
  group = aug,
  pattern = 'markdown',
  callback = function()
    vim.opt_local.expandtab = true
    vim.opt_local.shiftwidth = 2
    vim.opt_local.softtabstop = 2
  end,
})

-- Ensure new files always use Unix line endings
vim.api.nvim_create_autocmd('BufNewFile', {
  group = aug,
  pattern = '*',
  callback = function()
    vim.bo.fileformat = 'unix'
  end,
})

-- ---------------------------------------------------------------------------
-- Git diff colors + side-by-side command
-- ---------------------------------------------------------------------------
vim.cmd([[
  highlight DiffAdd    cterm=bold ctermbg=NONE ctermfg=22  gui=bold guibg=NONE guifg=#00FF00
  highlight DiffChange cterm=bold ctermbg=NONE ctermfg=208 gui=bold guibg=NONE guifg=#FFA500
  highlight DiffDelete cterm=bold ctermbg=NONE ctermfg=52  gui=bold guibg=NONE guifg=#FF0000

  command! Gitdiff vertical Gdiffsplit
]])
