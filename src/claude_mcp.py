# %%
# Imports #

import argparse
import os
import sys

from config import grandparent_dir, parent_dir
from utils import mcpservers_tools as mtools

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir

# The machine's single MCP config, in the user folder rather than at the clone
# root: .mcp.json is inherited by every directory beneath it (verified - a home
# copy resolves from a path nowhere near the clones), so one file here reaches
# every session on the machine, including repos checked out outside the clone
# root. It is safe to own precisely because it is generated: one writer, so the
# several credentials repos that declare servers cannot fight over it.
GENERATED_DEST = os.path.join(os.path.expanduser("~"), mtools.GENERATED_NAME)


# %%
# Generation #


def generate(dest=None, redact=False):
    """
    Build the merged document from every discovered declaration.
    Returns (document, dest, config_paths).
    """
    servers, config_paths = mtools.load_servers(CREDENTIALS_ROOT, REPO_ROOT)
    document = mtools.build_document(servers, REPO_ROOT, CREDENTIALS_ROOT, redact=redact)
    return document, dest or GENERATED_DEST, config_paths


def write(quiet=False, dest=None):
    """
    Regenerate the machine's .mcp.json. Returns the outcome string.

    Called by deploy_configs on every deploy, so the file is a product of what is
    cloned right now: add or remove a credentials repo and the next deploy adds
    or removes its servers with no per-machine file to edit.
    """
    document, target, config_paths = generate(dest=dest)
    outcome = mtools.write_document(target, document)
    if not quiet:
        names = ", ".join(document["mcpServers"]) or "no servers"
        sources = ", ".join(os.path.basename(path) for path in config_paths) or "no declarations found"
        print(f"mcp: {outcome} {target} ({names}) from {sources}")
    # never quiet: a declaring repo out of sync with its upstream means this
    # file and some other machine's file disagree, whatever this run printed
    for warning in mtools.sync_warnings(config_paths):
        print(warning)
    return outcome


# %%
# Entry point #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the machine's .mcp.json from every cloned repo's MCP server declarations."
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="print the document instead of writing it, with secret values redacted",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the file on disk is not what would be generated (writes nothing)",
    )
    parser.add_argument("--output", help="write somewhere other than ~/.mcp.json (for testing)")
    return parser.parse_args(argv)


def describe_discovery(target, config_paths):
    """
    Say what was searched, not just what was found. A server missing from the
    document is either a repo that is not cloned or a clone with no declaration
    yet, and those look the same in the output unless the scan is spelled out.
    """
    lines = [f"# would write {target}"]
    for path in config_paths:
        lines.append(f"#   declared by {os.path.relpath(path, CREDENTIALS_ROOT)}")
    silent = mtools.silent_overlay_dirs(CREDENTIALS_ROOT, config_paths)
    if silent:
        names = ", ".join(os.path.basename(path) for path in silent)
        lines.append(f"#   scanned, no {mtools.MCP_CONFIG_NAME} of its own: {names}")
    lines.append("#   accounts are NOT here - the server reads them at runtime, ask it for list_accounts")
    for warning in mtools.sync_warnings(config_paths):
        lines.append(f"# {warning}")
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    if args.print_only:
        document, target, config_paths = generate(dest=args.output, redact=True)
        print(describe_discovery(target, config_paths))
        print(mtools.serialize(document), end="")
        return 0
    if args.check:
        document, target, _ = generate(dest=args.output)
        if mtools.read_existing(target) == mtools.serialize(document):
            print(f"mcp: {target} is up to date")
            return 0
        print(f"mcp: {target} is stale - run deploy_configs.py deploy")
        return 1
    write(dest=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
