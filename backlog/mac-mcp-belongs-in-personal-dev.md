# mac_mcp: a macOS-only server lives in the repo every machine clones

    found:  2026-09-30
    status: open
    verify: git grep -n "def require_macos" src/utils/macmcp_tools.py && grep -ln "MAC_SERVER" ../personal_dev/src/*.py

The verify line prints the macOS guard, then the `personal_dev` scripts that
start this server. On 2026-09-30 it printed the guard at line 112 and four
scripts in `personal_dev/src/`.

Dotfiles holds configuration any machine can use and the code that
distributes and monitors it (`docs/repo_philosophy.md`). `src/mac_mcp.py` and
`src/utils/macmcp_tools.py` are neither, and they cannot run on most of the
machines that clone dotfiles.

## Evidence

- `require_macos()` raises on anything but darwin, so every tool fails on the
  Windows and Linux machines that clone this repo (see
  `mac-mcp-windows-linux.md`).
- Nothing in dotfiles calls it. Its callers are the `<context>_mac` server
  declarations in the credentials repos, and four scripts in
  `personal_dev/src/` that start it over stdio through
  `personal_dev/src/dotfiles_mcp.py`.
- It imports only `config`, `utils.inventory_tools` and its own
  `utils/macmcp_tools.py`. No other dotfiles module imports `macmcp_tools`.

## fix

1. Move `src/mac_mcp.py`, `src/utils/macmcp_tools.py`,
   `tests/test_mac_mcp.py`, `tests/test_macmcp_tools.py` and
   `docs/setup_mac_mcp.md` into `personal_dev` (`src/`, `tests/`, `docs/`).
   Bring over `find_credentials_dirs` and `credentials_context` from
   readable-utils `inventory_tools`, which `personal_dev` already depends on,
   instead of copying dotfiles' `utils/inventory_tools.py`.
2. Point every `<context>_mac` declaration at the new path. They use
   `{repo_root}/src/mac_mcp.py`, which `src/utils/mcpservers_tools.py`
   resolves to the dotfiles root, so add a placeholder for a sibling repo
   (`{git_dir}/personal_dev`) and use it in each declaration. Then check the
   generated `data/mcp/*.mcp.json`.
3. Rename `personal_dev/src/dotfiles_mcp.py` to match; it would no longer only
   start dotfiles servers.
4. Close `mac-mcp-windows-linux.md` in the same change. A Windows or Linux
   reader, if ever wanted, would be written in `personal_dev` too.
5. Delete the moved files here and re-run `uv run pytest -q` in both repos.

## blast radius

Every session that registers a `<context>_mac` server picks up the new path
on the next deploy, and one missed declaration leaves a server that fails to
start. Machines without `personal_dev` stop registering a server that could
never work there. No behaviour change on the personal Macs.

## not doing yet

It touches the MCP generator, every context's server declarations and four
scripts, so it wants its own change rather than riding along with another.
Decide the placeholder name in step 2 first.
