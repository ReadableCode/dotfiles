# Status board — single-pane TUI for the workday

`src/status_board.py` is a long-lived Textual TUI that shows, in one pane:
remote job/cron boards fetched over SSH (through jump hosts where needed) and
PRs awaiting your review across multiple GitHub accounts (and Bitbucket).
Panel definitions travel with the repos that own them, the same way
`deploy_configs.py` discovers overlay manifests.

```bash
cd ~/GitHub/dotfiles
uv sync
uv run python src/status_board.py           # the live board (q quits, r refreshes all)
uv run python src/status_board.py --once    # one static render, no TUI (sanity check)
```

PR titles are terminal hyperlinks — click to open in the browser (works in
iTerm2, WezTerm, Kitty, recent Windows Terminal, etc.).

## Where panels come from

On startup the board loads, in order:

1. `statusboard.yaml` in this repo's root, if present — tracked in the public
   repo, so **secrets-free panels only**;
2. `<context>_statusboard.yaml` in every sibling `*_credentials` repo
   (e.g. `fourteen_foods_credentials/fourteen_foods_statusboard.yaml`).

A machine only shows the panels of the credentials repos it has cloned —
clone a client's credentials repo and its panels appear, no central registry
to edit. Panel names must be unique across all loaded configs.

## Panel types

Every panel takes `name`, `type`, optional `interval` (seconds between
refreshes) and `note`.

### `ssh_command` — run a command on a remote machine and show its output

```yaml
- name: ff_vm_cron_jobs
  type: ssh_command
  host: ssh14vm            # inventory name or alias
  jump: ssh14              # optional jump hop (inventory name or alias)
  command: "bash ~/GitHub/fourteen_foods/backend/scripts/job_status.sh"
  interval: 300
  timeout: 90
```

`host` and `jump` resolve against the host inventories
(`<context>_hosts.json`): the config's own credentials repo is searched
first, then every other sibling inventory. The jump hop is injected on the
command line as `ssh -J user@host:port`, so the chain lives entirely in
config + inventory — **deliberately not in any machine's `~/.ssh/config`** —
and the board behaves identically on any machine with the credentials repos
cloned. When the board runs on the jump machine itself, the hop is skipped
automatically.

Requirements: non-interactive key auth to every hop (connections use
`BatchMode=yes`, so a password prompt = instant failure), and
`AllowTcpForwarding` enabled on the jump host's sshd (the default; needed
because `-J` tunnels through it — this works on Windows OpenSSH Server too).
ANSI colors in the command's output are rendered as-is.

### `github_prs` — PRs awaiting your review, one panel per account

```yaml
- name: github_personal_prs
  type: github_prs
  token_env: GH_PAT_PERSONAL
  env_file: personal.env    # optional, relative to the config's repo
  interval: 180
```

Uses the search API (`is:open is:pr review-requested:<you>`); the account is
whoever the token belongs to, so two accounts = two panels with different
`token_env` names. Two panels can also share ONE account with different
fine-grained tokens: the search only returns repos a token was granted, so a
client repo hosted under a personal account gets its own panel via a
single-repo PAT (which then lives in that client's credentials repo). Add
optional `search:` qualifiers (e.g. `-repo:owner/name`) to keep an
all-repos panel from overlapping a single-repo one. Tokens resolve from the real environment first, then the
`env_file` — tokens never go in the statusboard config itself. Putting the
token in the credentials repo's env file is the intended setup: any machine
with the repo cloned gets a working board, no shell exports or gh CLI needed.

The PAT only needs **read** access (unlike the read+write MCP tokens in
`docs/setup_claude_github_mcp.md`, which submit reviews):

- fine-grained token (recommended): `Pull requests: Read` — `Metadata: Read`
  is included automatically — granted on the repos you review in (or all
  repos of the account);
- classic token: `repo` scope if any repo is private (classic has no
  read-only option); no scopes for public-only.

Org tokens must be SSO-authorized or searches silently return nothing
(account specifics live in the private credentials repos).

### `bitbucket_prs` — open PRs listing you as reviewer

```yaml
- name: ff_bitbucket_prs
  type: bitbucket_prs
  workspace: some-workspace
  repos: [repo-a, repo-b]   # omit to scan every repo in the workspace (slower)
  username_env: BB_USERNAME
  app_password_env: BB_APP_PASSWORD
  env_file: fourteen_foods.env
```

Auth is a Bitbucket app password (Account settings → App passwords, scopes:
Account read + Pull requests read). Bitbucket has no cross-workspace
"review requested" search, so the board queries per repo — list the repos you
care about to keep it fast.

## Viewing from a personal device

The board runs wherever the credentials/keys live and you view it from
anywhere on the LAN — e.g. run it in tmux on the Mac and attach from a phone
or tablet over SSH (Blink/Termius render Textual fine). Textual can also
serve any app as a web page (`uv run textual serve "python src/status_board.py"`,
needs `textual-dev`) if a browser tab ever beats a terminal.
