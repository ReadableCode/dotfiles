# Slack MCP — searching and reading a workspace from Claude Code

Registers a stdio MCP server that lets Claude Code search a Slack workspace and
read channel history — e.g. "what version of $vendor_client are other Linux
users on". Workspace names, channel names and app IDs are deliberately NOT here:
this repo is public, so they live in a note in the matching private
`*_credentials` repo (same rule as `setup_claude_github_mcp.md`).

## Which server

Use **`slack-mcp-server`** (github.com/korotovsky/slack-mcp-server, npm
`slack-mcp-server`, MIT, Go binary wrapped for npx). Three reasons:

* It is the only well-maintained option that exposes
  **`conversations_search_messages`** — searching is the whole point here, and
  most Slack MCP servers only read channels you name explicitly.
* It runs as a **local stdio subprocess over npx with a token in the
  environment**, which is exactly the shape `mcp_servers.yaml` declarations
  already have (`command` + `args` + `env_secrets`). Nothing new to build.
* Write tools are **off by default** and gated behind their own env vars, so a
  read-only deployment is the default rather than something to remember.

Two options that look right and are not:

* **`@modelcontextprotocol/server-slack`** — the reference server named in older
  guides. It is no longer in `modelcontextprotocol/servers` (`src/` is down to
  `everything`, `fetch`, `filesystem`, `git`, `memory`, `sequentialthinking`,
  `time`) and it never supported search anyway.
* **Slack's own hosted MCP server** at `https://mcp.slack.com/mcp` — real, and
  Claude Code is a listed partner client, but it is **remote JSON-RPC over
  Streamable HTTP with OAuth**, and `src/utils/mcpservers_tools.py` requires a
  `command` and knows only `args`/`env`/`env_secrets`/`env_file`. There is no
  `type`/`url`/`headers` key, so a remote server cannot be declared through the
  generator at all without extending it — and every client must be "backed by a
  registered Slack app with a fixed app ID" that a **workspace admin approves**,
  so it is not the lower-friction path it appears to be. Revisit only if the
  generator grows HTTP support.

## The token type trap

`search.messages` is a **user-token method**. Its only documented scope is
`search:read` under a *User token* heading; there is no bot-token entry, and a
bot token gets `not_allowed_token_type` back. `slack-mcp-server` says the same
thing out loud: `conversations_search_messages` is "not available when using bot
tokens (`xoxb-*`)".

So this needs an **`xoxp-` user token**, not the `xoxb-` bot token a context's
existing notification bot already has. A bot token cannot be made to work by
adding scopes — `search:read.public` exists for bots but does not reach this
method through this server. Budget for minting a new token; an existing bot
token in the env file is not reusable here.

A user token also means every call is **you**: it sees exactly the channels your
account is in, and search results are shaped by the search filters set in your
Slack UI. Nothing it reads is anything you could not already read.

## Scopes for read-only search

Minimum set for "search public channels and read the matching messages":

| Scope | Why |
|---|---|
| `search:read` | `conversations_search_messages` — the only way to find messages you don't already know the channel of |
| `channels:read` | resolve `#channel-name` ↔ channel ID, populate `channels_list` |
| `channels:history` | actually read messages and threads in public channels |
| `users:read` | resolve author IDs to names, so results are legible |

Add **only if** you also need private channels you are a member of:
`groups:read`, `groups:history`. Skip `im:*` / `mpim:*` (DMs), `chat:write`,
`channels:write` and `usergroups:write` entirely — none are needed to read, and
`chat:write` on a *user* token means an agent can post as you.

## Creating the app

1. api.slack.com/apps → **Create New App** → *From an app manifest*, and paste a
   manifest whose `oauth_config.scopes.user` is exactly the table above, with
   `org_deploy_enabled`, `socket_mode_enabled` and `token_rotation_enabled` all
   `false`. (From-scratch works too; the manifest just avoids clicking 4 scopes.)
2. **OAuth & Permissions → Install to Workspace.**
3. Copy the **User OAuth Token** — it starts `xoxp-`. The Bot User OAuth Token
   (`xoxb-`) on the same page is the wrong one; see above.

**This step is where it stops if the workspace requires app approval.** Most
managed workspaces (and every Enterprise Grid org that has turned on app
management) queue "Install to Workspace" for a **workspace/org admin** to
approve, and a normal member cannot self-approve. Check
`https://<workspace>.slack.com/apps/manage` first: if it shows a *Request
Configuration* / *Request to install* button instead of *Install*, you are
submitting a request and the timeline is somebody else's. Do that before minting
anything else — the scopes and the declaration below are useless without the
token, and there is no local workaround that is also policy-compliant.

## Where the token goes

Never in `mcp_servers.yaml` — that file is tracked. The token goes in the
declaring `*_credentials` repo's **env file** (the same `KEY=value` file its jira
and calendar-board secrets already use; check that repo, the filename is
per-context and not `.env`), and the declaration names the *variable*:

```
SLACK_USER_TOKEN=xoxp-...
```

`env_secrets` maps the var the server expects → the var to resolve out of
`env_file`, through `src/utils/secret_tools.py` (real environment wins first).
The generated `~/.mcp.json` is written `0600` precisely because it ends up
holding the resolved value.

## The declaration

Per the `src/` rules in `CLAUDE.md`: **dotfiles declares nothing here.** Which
workspace a Slack server reaches is a context question, so the declaration lives
in that context's `<context>_credentials/<context>_mcp_servers.yaml`, named for
the context — an unlabeled `slack` on a machine holding several contexts is
exactly the ambiguity context-prefixed names exist to prevent.

```yaml
- name: acme_slack
  command: npx
  args: ["-y", "slack-mcp-server@latest", "--transport", "stdio"]
  env:
    SLACK_MCP_ENABLED_TOOLS: "conversations_search_messages,conversations_history,conversations_replies,channels_list"
  env_secrets:
    SLACK_MCP_XOXP_TOKEN: SLACK_USER_TOKEN
  env_file: acme.env
```

`SLACK_MCP_ENABLED_TOOLS` is an allowlist, and pinning it is worth the line:
unset, the server also registers the usergroups tools, and `usergroups_write`
would only need a scope added to the app to become live. Four named read tools
cannot drift. The write gates (`SLACK_MCP_ADD_MESSAGE_TOOL`,
`SLACK_MCP_REACTION_TOOL`, `SLACK_MCP_MARK_TOOL`, `SLACK_MCP_ATTACHMENT_TOOL`)
default off and stay unset.

**Add the token before the declaration.** `env_secrets` resolves at generate
time and an unresolvable var raises, so a declaration committed ahead of its
token fails `claude_mcp.py` — which means every `deploy_configs.py deploy` on
every machine with that repo cloned exits non-zero, not just this one.

## Registering it

Regeneration, not `claude mcp add` — see `setup_google_mcp.md` for why the
generated `~/.mcp.json` is the only writer:

```bash
uv run python src/claude_mcp.py --print   # confirm acme_slack appears, token redacted
uv run python src/deploy_configs.py deploy
```

First use in a given directory needs the one-time in-session approval ("New MCP
server found in this project"); `claude mcp list` shows `⏸ Pending approval`
until then. npx fetches the Go binary on first launch, so the first call is slow
and needs network.

## Troubleshooting

`not_allowed_token_type` — a `xoxb-` token reached a user-token method. Wrong
token off the OAuth page.

`missing_scope` — the app was installed before a scope was added. Adding scopes
requires **reinstalling** the app, and reinstalling reissues the token; the old
one keeps working with the old scopes, which reads as the change silently not
applying. Re-copy the token into the env file.

`channels_list` empty, or `#channel-name` / `@user` not resolving — the users
and channels caches (`~/.cache/slack-mcp-server/`) have not been built.
Numeric `C…` channel IDs still work meanwhile.

## The fallback that isn't recommended

The server also accepts `xoxc-` + `xoxd-` — a browser session token plus the `d`
cookie, scraped from your own logged-in Slack tab. It needs no app and no admin
approval at all, which is why the package advertises it.

Do not reach for it on a work machine without asking first. It is your live
session credential sitting in a config file with no scope limits, it breaks
whenever the session rotates, and copying a session cookie out of the browser is
the kind of thing that is against an acceptable-use policy even when the intent
is read-only. If app approval is refused, that is an answer to accept, not to
route around.
