# GitHub CLI

## Installation

### Linux (Ubuntu/Debian)

```bash
sudo apt install gh
```

### Linux (Fedora)

```bash
sudo dnf install -y gh
```

### macOS

```bash
brew install gh
```

### Windows (Chocolatey)

```powershell
choco install gh
```

### Windows (winget)

```powershell
winget install --id GitHub.cli
```

## Authenticating

Run and follow the prompts (choose HTTPS or SSH, then browser or token):

```bash
gh auth login
```

Verify authentication:

```bash
gh auth status
```

## Pull Requests

List open PRs:

```bash
gh pr list
```

List closed PRs:

```bash
gh pr list --state closed
```

View a PR (opens in browser):

```bash
gh pr view <pull-request-number> --web
```

Create a PR (interactive):

```bash
gh pr create
```

Create a PR with title and body:

```bash
gh pr create --title "My feature" --body "Description"
```

Check PR CI status:

```bash
gh pr checks <pull-request-number>
```

Merge a PR:

```bash
gh pr merge <pull-request-number>
```

Checkout a PR branch locally:

```bash
gh pr checkout <pull-request-number>
```

## Issues

List open issues:

```bash
gh issue list
```

Create an issue:

```bash
gh issue create --title "Bug title" --body "Description"
```

View an issue:

```bash
gh issue view <issue-number>
```

Close an issue:

```bash
gh issue close <issue-number>
```

## Repositories

Clone a repo:

```bash
gh repo clone <owner>/<repo>
```

Create a new repo:

```bash
gh repo create <repo-name> --public
```

View repo in browser:

```bash
gh repo view --web
```

Fork a repo:

```bash
gh repo fork <owner>/<repo>
```

## Workflows / Actions

List workflow runs:

```bash
gh run list
```

View a run's logs:

```bash
gh run view <run-id> --log
```

Watch a running workflow:

```bash
gh run watch <run-id>
```

Trigger a workflow manually:

```bash
gh workflow run <workflow-name>
```
