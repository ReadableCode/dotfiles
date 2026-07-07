# Claude Code GitHub MCP — multiple accounts

Pattern for registering one GitHub MCP server per GitHub account (e.g. a
personal account plus a client/work account) so Claude Code can act on both.
Account names, org details, and any client-specific quirks are deliberately
NOT documented here — they live in a note in the matching private credentials
repo (see the `*_credentials` repos next to this checkout).

You need a fine-grained Personal Access Token per account, scoped to the
relevant repos, with at minimum:

- Pull requests: Read and write (to list/diff PRs and submit reviews)
- Contents: Read

Generate one PAT under each GitHub account at
Settings → Developer settings → Personal access tokens → Fine-grained tokens.
Store them as env vars rather than pasting into config — e.g. add to your
shell's machine-local file (`.zshrc.local`, not this shared repo):

```bash
export GH_PAT_PERSONAL="..."
export GH_PAT_WORK="..."
```

Then register a separate MCP server entry per account:

```bash
claude mcp add github-personal \
  -- npx -y @modelcontextprotocol/server-github \
  --env GITHUB_PERSONAL_ACCESS_TOKEN="$GH_PAT_PERSONAL"

claude mcp add github-work \
  -- npx -y @modelcontextprotocol/server-github \
  --env GITHUB_PERSONAL_ACCESS_TOKEN="$GH_PAT_WORK"
```

(Exact package/binary name may differ if Anthropic or GitHub has shipped a newer
official server — check `claude mcp` docs if `@modelcontextprotocol/server-github`
404s. Search before assuming.)

Verify both are visible with `claude mcp list`, then `/mcp` inside a Claude Code
session to confirm both servers show as connected.

If an org requires SSO-authorized PATs, authorize the token for the org under
Settings → Developer settings → Personal access tokens → "Configure SSO" after
creating it, or that server's calls will silently return zero repos.
