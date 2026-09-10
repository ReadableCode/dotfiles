#!/usr/bin/env python3
"""
context_leak_check.py - refuse identifiers of one context inside another.

Stdlib-only, so a git hook can run it with bare python3 before any venv
exists. Every context's identifiers are DERIVED from that context's own
sibling ``<context>_credentials`` repo, so this public file names no client:

- the context token and its spelling variants (``acme_co`` -> ``acme-co``,
  ``acme co``, ``acmeco``)
- every ``name``, ``dir`` and non-personal ``org`` in ``<context>_repos.yaml``
- every host ``name``, ``hostname`` and ssh alias in ``<context>_hosts.json``
- every ``Host`` name in the repo's ``ssh/*.conf`` fragments
- ``JIRA_PROJECT=`` values in that repo's ``*.env`` files (ticket prefixes),
  and the hostname of every URL-shaped value in them (never the values
  themselves: an env file is mostly secrets)
- the name of any sibling dev repo whose ``<dirname>_manifest.yaml`` targets
  the context with ``per_context_repo``
- one identifier per line from an optional ``<context>_identifiers.txt``
  (display names, anything not derivable)

Rules, by the repo being scanned:

- the personal context's own repos (``personal_credentials``, ``personal_dev``,
  any ``personal_*`` sibling): anything goes; they are the private places that
  know every context by name.
- a client context's credentials or dev repo: the OTHER clients' identifiers
  are forbidden.
- every other repo (dotfiles and the personal repos, public or not): every
  client's identifiers are forbidden.

Usage:
  context_leak_check.py                   scan dotfiles + every credentials/dev repo (tracked files)
  context_leak_check.py --repo <path>     scan one repo's tracked files
  context_leak_check.py --repo <path> --staged   scan only what is staged (the pre-commit hook)
  context_leak_check.py --all             also scan every other sibling repo (report only)
  context_leak_check.py --list            print the derived identifiers per context

Exit 1 on any hit (except under --all for the extra repos, which only report).
"""

import argparse
import json
import os
import re
import subprocess
import sys

CREDENTIALS_SUFFIX = "_credentials"
PERSONAL_CONTEXT = "personal"
MIN_IDENTIFIER_LEN = 4
MAX_FILE_BYTES = 2_000_000
TEXT_SUFFIXES = None  # every tracked file that decodes as UTF-8


def repo_parent():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# %%
# Identifier derivation #


def _read_yaml_ish_repos(path):
    """
    Minimal reader for <context>_repos.yaml: collects name:, dir: and org:
    values without a yaml dependency (stdlib only, hook-safe).
    """
    names, orgs = [], []
    if not os.path.exists(path):
        return names, orgs
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.split("#", 1)[0].strip()
            match = re.match(r"-?\s*(name|dir|org):\s*(.+)$", line)
            if not match:
                continue
            key, value = match.group(1), match.group(2).strip().strip("'\"")
            if not value:
                continue
            (orgs if key == "org" else names).append(value)
    return names, orgs


def _read_hosts(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    hosts = data.get("hosts", data) if isinstance(data, dict) else data
    out = []
    for host in hosts if isinstance(hosts, list) else []:
        if not isinstance(host, dict):
            continue
        for key in ("name", "hostname"):
            value = host.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value.strip())
        for alias in host.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                out.append(alias.strip())
    return out


def _read_ssh_hosts(credentials_dir):
    """Every ``Host`` name in the repo's ssh fragments (addresses are already in the inventory)."""
    names = []
    ssh_dir = os.path.join(credentials_dir, "ssh")
    if not os.path.isdir(ssh_dir):
        return names
    for entry in sorted(os.listdir(ssh_dir)):
        try:
            with open(os.path.join(ssh_dir, entry), "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    match = re.match(r"\s*Host\s+(.+)$", line)
                    if match:
                        names.extend(token for token in match.group(1).split() if not re.fullmatch(r"[\d.]+", token))
        except OSError:
            continue
    return names


# Hostnames under these domains are third-party services every context uses
# (Google APIs, GitHub, AWS, ...); a URL to one identifies nobody.
GENERIC_URL_DOMAINS = (
    "google.com", "googleapis.com", "googleusercontent.com", "github.com", "githubusercontent.com",
    "amazonaws.com", "microsoft.com", "microsoftonline.com", "office.com", "graph.microsoft.com",
    "slack.com", "ntfy.sh", "openai.com", "anthropic.com", "cloudflare.com", "bitbucket.org",
)


def _generic_host(host):
    return any(host == domain or host.endswith("." + domain) for domain in GENERIC_URL_DOMAINS)


def _read_env_url_hosts(credentials_dir):
    """Hostnames of URL-shaped env values (a Jira site, a vault, a hub); nothing else from an env file."""
    hosts = []
    for entry in sorted(os.listdir(credentials_dir)):
        if not entry.endswith(".env"):
            continue
        try:
            with open(os.path.join(credentials_dir, entry), "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    for match in re.finditer(r"https?://([A-Za-z0-9.-]+)", line):
                        host = match.group(1).lower()
                        if (
                            "." in host
                            and not re.fullmatch(r"[\d.]+", host)
                            and host != "localhost"
                            and not _generic_host(host)
                        ):
                            hosts.append(host)
        except OSError:
            continue
    return hosts


def _read_ticket_prefixes(credentials_dir):
    prefixes = []
    for entry in sorted(os.listdir(credentials_dir)):
        if not entry.endswith(".env"):
            continue
        try:
            with open(os.path.join(credentials_dir, entry), "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    match = re.match(r"\s*(?:export\s+)?JIRA_PROJECT\s*=\s*['\"]?([A-Za-z][A-Za-z0-9_]+)", line)
                    if match:
                        prefixes.append(match.group(1).upper() + "-")
        except OSError:
            continue
    return prefixes


def _read_identifier_file(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.startswith("#")]


def _dev_repos_for(context, parent):
    """Sibling dirs whose <dirname>_manifest.yaml targets this context via per_context_repo."""
    found = []
    for entry in sorted(os.listdir(parent)):
        if entry.endswith(CREDENTIALS_SUFFIX) or entry == "dotfiles":
            continue
        manifest = os.path.join(parent, entry, f"{entry}_manifest.yaml")
        if not os.path.isfile(manifest):
            continue
        with open(manifest, "r", encoding="utf-8", errors="ignore") as handle:
            text = handle.read()
        targets = re.findall(r"per_context_repo:\s*(.+)", text)
        for target in targets:
            values = re.findall(r"[A-Za-z0-9_]+", target)
            if context in values:
                found.append(entry)
                break
    return found


def token_variants(token):
    variants = {token, token.replace("_", "-"), token.replace("_", " "), token.replace("_", "")}
    return {v for v in variants if v}


def derive_contexts(parent=None):
    """
    {context: {"identifiers": set, "repos": [dirs belonging to the context]}}
    for every sibling credentials repo except the personal one.
    """
    parent = parent or repo_parent()
    personal_orgs = set()
    personal_dir = os.path.join(parent, PERSONAL_CONTEXT + CREDENTIALS_SUFFIX)
    if os.path.isdir(personal_dir):
        _, personal_orgs_list = _read_yaml_ish_repos(os.path.join(personal_dir, f"{PERSONAL_CONTEXT}_repos.yaml"))
        personal_orgs = {o.lower() for o in personal_orgs_list}
    contexts = {}
    for entry in sorted(os.listdir(parent)):
        if not entry.endswith(CREDENTIALS_SUFFIX) or not os.path.isdir(os.path.join(parent, entry)):
            continue
        context = entry[: -len(CREDENTIALS_SUFFIX)]
        if context == PERSONAL_CONTEXT:
            continue
        cdir = os.path.join(parent, entry)
        identifiers = set(token_variants(context)) | {entry}
        names, orgs = _read_yaml_ish_repos(os.path.join(cdir, f"{context}_repos.yaml"))
        identifiers |= set(names)
        identifiers |= {o for o in orgs if o.lower() not in personal_orgs}
        identifiers |= set(_read_hosts(os.path.join(cdir, f"{context}_hosts.json")))
        identifiers |= set(_read_ticket_prefixes(cdir))
        identifiers |= set(_read_ssh_hosts(cdir))
        identifiers |= set(_read_env_url_hosts(cdir))
        identifiers |= set(_read_identifier_file(os.path.join(cdir, f"{context}_identifiers.txt")))
        dev_repos = _dev_repos_for(context, parent)
        for dev in dev_repos:
            identifiers |= token_variants(dev)
        identifiers = {i for i in identifiers if len(i) >= MIN_IDENTIFIER_LEN}
        # "repos": the context's own two-or-more repos, scanned by default.
        # "owned": every checkout the context's repos file declares as well -
        # the client's own repositories, which naturally carry their own
        # identifiers and are never scanned by default (they are the client's).
        owned = set(names)
        contexts[context] = {
            "identifiers": identifiers,
            "repos": [entry] + dev_repos,
            "owned": owned | {entry} | set(dev_repos),
        }
    return contexts


# %%
# Scanning #


def _pattern(identifier):
    escaped = re.escape(identifier)
    if identifier.endswith("-"):
        return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?=[0-9])", re.IGNORECASE)
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.IGNORECASE)


def _git(repo_dir, *args):
    return subprocess.run(["git", "-C", repo_dir] + list(args), capture_output=True, text=True, errors="replace")


def checkout_name(repo_dir):
    """The directory name the context rules know this checkout by.

    A git worktree lives under any path (T3 Code cuts them into ``~/.t3/worktrees/<repo>/<id>``),
    so its own folder name identifies nothing; the checkout it belongs to is the parent of the
    common git dir. A plain checkout is its own name.
    """
    result = _git(repo_dir, "rev-parse", "--git-common-dir")
    common = result.stdout.strip()
    if result.returncode == 0 and common:
        if not os.path.isabs(common):
            common = os.path.join(repo_dir, common)
        return os.path.basename(os.path.dirname(os.path.normpath(common)))
    return os.path.basename(os.path.normpath(repo_dir))


def forbidden_for(repo_dir, contexts):
    """Which contexts' identifiers may not appear in this repo (None = no rule)."""
    name = checkout_name(repo_dir)
    if name == PERSONAL_CONTEXT or name.startswith(PERSONAL_CONTEXT + "_"):
        return {}
    owner = next((c for c, info in contexts.items() if name in info["owned"]), None)
    return {c: info for c, info in contexts.items() if c != owner}


def tracked_files(repo_dir):
    result = _git(repo_dir, "ls-files", "-z")
    return [p for p in result.stdout.split("\0") if p] if result.returncode == 0 else []


def staged_files(repo_dir):
    result = _git(repo_dir, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [p for p in result.stdout.split("\0") if p] if result.returncode == 0 else []


def read_content(repo_dir, path, staged):
    if staged:
        result = _git(repo_dir, "show", f":{path}")
        return result.stdout if result.returncode == 0 else ""
    full = os.path.join(repo_dir, path)
    try:
        if os.path.getsize(full) > MAX_FILE_BYTES or os.path.islink(full):
            return ""
        with open(full, "rb") as handle:
            raw = handle.read()
    except OSError:
        return ""
    if b"\0" in raw[:4096]:
        return ""
    return raw.decode("utf-8", errors="replace")


def scan_repo(repo_dir, contexts, staged=False):
    """[(path, line_no, context, identifier, line_text)] for every forbidden hit."""
    rules = forbidden_for(repo_dir, contexts)
    if not rules:
        return []
    patterns = [
        (context, ident, _pattern(ident))
        for context, info in rules.items()
        for ident in sorted(info["identifiers"])
    ]
    hits = []
    for path in staged_files(repo_dir) if staged else tracked_files(repo_dir):
        content = read_content(repo_dir, path, staged)
        if not content:
            continue
        for line_no, line in enumerate(content.split("\n"), 1):
            for context, ident, pattern in patterns:
                if pattern.search(line):
                    hits.append((path, line_no, context, ident, line.strip()[:120]))
    return hits


def default_scan_set(parent, contexts):
    repos = [os.path.join(parent, "dotfiles")]
    for info in contexts.values():
        repos += [os.path.join(parent, r) for r in info["repos"]]
    return [r for r in repos if os.path.isdir(os.path.join(r, ".git")) or os.path.isfile(os.path.join(r, ".git"))]


def all_sibling_repos(parent):
    out = []
    for entry in sorted(os.listdir(parent)):
        path = os.path.join(parent, entry)
        if os.path.isdir(os.path.join(path, ".git")):
            out.append(path)
    return out


def report(hits, repo_dir):
    for path, line_no, context, ident, text in hits:
        print(f"{os.path.basename(repo_dir)}/{path}:{line_no}: [{context}] {ident!r}: {text}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", help="scan this repo only (default: dotfiles + every credentials/dev repo)")
    parser.add_argument("--staged", action="store_true", help="scan the staged content of --repo (pre-commit)")
    parser.add_argument("--all", action="store_true", help="also report on every other sibling repo")
    parser.add_argument("--list", action="store_true", help="print the derived identifiers per context and exit")
    parser.add_argument("--parent", help="the directory holding the sibling repos (default: dotfiles' parent)")
    args = parser.parse_args(argv)
    parent = os.path.abspath(args.parent) if args.parent else repo_parent()
    contexts = derive_contexts(parent)
    if args.list:
        for context, info in contexts.items():
            print(f"{context} ({', '.join(info['repos'])}):")
            for ident in sorted(info["identifiers"], key=str.lower):
                print(f"  {ident}")
        return 0
    if not contexts:
        print("context-leak: no client credentials repos cloned here; nothing to check")
        return 0
    failed = False
    if args.repo:
        repo = os.path.abspath(args.repo)
        hits = scan_repo(repo, contexts, staged=args.staged)
        report(hits, repo)
        if hits:
            print(f"context-leak: {len(hits)} hit(s) in {os.path.basename(repo)} - another context's identifier "
                  f"must not appear here; describe the pattern generically instead")
            return 1
        return 0
    for repo in default_scan_set(parent, contexts):
        hits = scan_repo(repo, contexts)
        report(hits, repo)
        failed = failed or bool(hits)
    if args.all:
        checked = {os.path.normpath(r) for r in default_scan_set(parent, contexts)}
        for repo in all_sibling_repos(parent):
            if os.path.normpath(repo) in checked or os.path.basename(repo).startswith(PERSONAL_CONTEXT + "_"):
                continue
            hits = scan_repo(repo, contexts)
            if hits:
                print(f"-- {os.path.basename(repo)} (report only):")
                report(hits, repo)
    outcome = "FAILED" if failed else "clean"
    repo_count = len(default_scan_set(parent, contexts))
    ident_count = sum(len(i["identifiers"]) for i in contexts.values())
    print(f"context-leak: {outcome} across {repo_count} repos, "
          f"{ident_count} identifiers from {len(contexts)} contexts")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
