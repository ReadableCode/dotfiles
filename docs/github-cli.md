# GitHub CLI

## Installation

Linux:

```bash
sudo apt install gh
```

Windows:
  
```bash
choco install gh
```

## Authenticating

```bash
gh auth login
```

## Listing Pull Requests

Open:

```bash
gh pr list
```

Closed:

```bash
gh pr list --state closed
```

## Creating Pull Requests

```bash
gh pr create
```

## Checks

```bash
gh pr checks <pull-request-number>
```
