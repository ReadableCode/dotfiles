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

# One generated document per declaring context, in dotfiles' gitignored data/
# folder. The per-repo manifest entries (per_context_repo, see
# docs/deploy_configs.md) link <context>.mcp.json into every checkout of that
# context as <repo>/.mcp.json, so a session inside a client repo registers that
# client's servers and nothing else - no file anywhere names another context's
# servers. Generated rather than committed because the content is
# machine-specific (absolute clone paths, resolved secrets); safe to own
# because there is one writer.
GENERATED_DIR = os.path.join(REPO_ROOT, mtools.GENERATED_DIRNAME)


# %%
# Generation #


def generate(output_dir=None, redact=False):
    """
    Build every context's document from the discovered declarations.
    Returns (documents, output_dir, config_paths) with documents keyed by
    context; a context that declares no servers gets no document.
    """
    servers, config_paths = mtools.load_servers(CREDENTIALS_ROOT, REPO_ROOT)
    documents = mtools.build_documents(servers, REPO_ROOT, CREDENTIALS_ROOT, redact=redact)
    return documents, output_dir or GENERATED_DIR, config_paths


def target_path(output_dir, context):
    return os.path.join(output_dir, mtools.generated_filename(context))


def write(quiet=False, output_dir=None):
    """
    Regenerate every context's file and delete the ones no cloned repo declares
    any more. Returns {path: outcome}.

    Called by deploy_configs before it builds its plan, so each file is a product
    of what is cloned right now and exists before the per-repo entries that link
    it are evaluated: add or remove a credentials repo and the next deploy adds
    or removes its servers with no per-machine file to edit.
    """
    documents, target_dir, config_paths = generate(output_dir=output_dir)
    outcomes = {}
    for context, document in documents.items():
        target = target_path(target_dir, context)
        outcomes[target] = mtools.write_document(target, document)
        if not quiet:
            names = ", ".join(document["mcpServers"])
            print(f"mcp: {outcomes[target]} {target} ({names})")
    for stale in mtools.stale_generated_files(target_dir, documents):
        os.remove(stale)
        outcomes[stale] = "removed"
        if not quiet:
            print(f"mcp: removed {stale} (no cloned repo declares that context any more)")
    if not quiet and not documents:
        print("mcp: no servers declared by any cloned repo; nothing generated")
    # never quiet: a declaring repo out of sync with its upstream means these
    # files and some other machine's files disagree, whatever this run printed
    for warning in mtools.sync_warnings(config_paths):
        print(warning)
    return outcomes


# %%
# Entry point #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate one .mcp.json per context (data/mcp/<context>.mcp.json) from every cloned repo's "
        "MCP server declarations."
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="print the documents instead of writing them, with secret values redacted",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any file on disk is not what would be generated (writes nothing)",
    )
    parser.add_argument("--output", help="write into a directory other than data/mcp (for testing)")
    return parser.parse_args(argv)


def describe_discovery(target_dir, config_paths):
    """
    Say what was searched, not just what was found. A server missing from a
    document is either a repo that is not cloned or a clone with no declaration
    yet, and those look the same in the output unless the scan is spelled out.
    """
    lines = [f"# would write into {target_dir}"]
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
        documents, target_dir, config_paths = generate(output_dir=args.output, redact=True)
        print(describe_discovery(target_dir, config_paths))
        for context, document in documents.items():
            print(f"# {mtools.generated_filename(context)}")
            print(mtools.serialize(document), end="")
        return 0
    if args.check:
        documents, target_dir, _ = generate(output_dir=args.output)
        stale = [
            target_path(target_dir, context)
            for context, document in documents.items()
            if mtools.read_existing(target_path(target_dir, context)) != mtools.serialize(document)
        ] + mtools.stale_generated_files(target_dir, documents)
        if not stale:
            print(f"mcp: {target_dir} is up to date")
            return 0
        print(f"mcp: stale - run deploy_configs.py deploy: {', '.join(stale)}")
        return 1
    write(output_dir=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
