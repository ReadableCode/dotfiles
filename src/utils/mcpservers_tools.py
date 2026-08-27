# %%
# Imports #

import json
import os

import yaml
from utils.inventory_tools import credentials_context, find_credentials_dirs
from utils.secret_tools import resolve_secret

# %%
# Variables #

MCP_CONFIG_NAME = "mcp_servers.yaml"
GENERATED_NAME = ".mcp.json"
REQUIRED_SERVER_KEYS = ("name", "command")
KNOWN_SERVER_KEYS = REQUIRED_SERVER_KEYS + ("args", "env", "env_secrets", "env_file")
REDACTED = "***"

# Placeholders expanded in command/args/env so a declaration never carries an
# absolute path: deploy has no templating, and a machine-specific path baked
# into a shared file points every machine at one machine's clone.
REPO_ROOT_TOKEN = "{repo_root}"
REPO_PARENT_TOKEN = "{repo_parent}"


# %%
# Discovery #


def discover_mcp_configs(credentials_root, repo_root=None):
    """
    Locate every MCP server declaration: an optional ``mcp_servers.yaml`` in the
    dotfiles repo root (tracked, so no secret values - only env var names) plus,
    for each sibling ``*_credentials`` repo, an optional
    ``<context>_mcp_servers.yaml``. Same overlay pattern as the calendar board
    and the googlemail configs. Returns a list of (config_path, base_dir) pairs.
    """
    configs = []
    if repo_root:
        main_config = os.path.join(repo_root, MCP_CONFIG_NAME)
        if os.path.exists(main_config):
            configs.append((main_config, repo_root))
    for credentials_dir in find_credentials_dirs(credentials_root):
        overlay = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_{MCP_CONFIG_NAME}")
        if os.path.exists(overlay):
            configs.append((overlay, credentials_dir))
    return configs


def load_servers(credentials_root, repo_root=None, config_path=None):
    """
    Load every discovered declaration, returning (servers, config_paths).

    Merging here is the whole point: each repo DECLARES the servers it owns and
    one generator writes one file, so two credentials repos can never fight over
    the single fixed name ``.mcp.json`` the way they would if each deployed its
    own copy. Server names must be unique across all configs - a collision is a
    real conflict between repos and has to be resolved by renaming, not by
    letting load order decide.
    """
    if config_path:
        located = [(config_path, os.path.dirname(os.path.abspath(config_path)))]
    else:
        located = discover_mcp_configs(credentials_root, repo_root)
    servers = []
    seen: dict = {}
    for path, base_dir in located:
        for server in _parse_server_config(path):
            if server["name"] in seen:
                raise ValueError(
                    f"Duplicate MCP server name '{server['name']}' in {path} "
                    f"(already declared in {seen[server['name']]})"
                )
            seen[server["name"]] = path
            server["_base_dir"] = base_dir
            server["_config"] = path
            servers.append(server)
    return servers, [path for path, _ in located]


def _parse_server_config(config_path):
    """Validate one declaration file into a list of server mappings."""
    with open(config_path, "r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle) or []
    if not isinstance(parsed, list):
        raise ValueError(f"MCP config {config_path} must be a YAML list of server declarations")
    servers = []
    for server in parsed:
        if not isinstance(server, dict):
            raise ValueError(f"MCP server declaration in {config_path} must be a mapping: {server}")
        missing = [key for key in REQUIRED_SERVER_KEYS if not server.get(key)]
        if missing:
            raise ValueError(f"MCP server declaration in {config_path} is missing {', '.join(missing)}: {server}")
        unknown = [key for key in server if key not in KNOWN_SERVER_KEYS]
        if unknown:
            raise ValueError(
                f"MCP server '{server['name']}' in {config_path} has unknown keys: {', '.join(sorted(unknown))}"
            )
        _validate_shapes(server, config_path)
        servers.append(dict(server))
    return servers


def _validate_shapes(server, config_path):
    """args must be a list of strings; env/env_secrets flat string maps."""
    args = server.get("args", [])
    if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
        raise ValueError(f"MCP server '{server['name']}' in {config_path} has non-string args: {args}")
    for key in ("env", "env_secrets"):
        mapping = server.get(key, {})
        if not isinstance(mapping, dict) or any(
            not isinstance(name, str) or not isinstance(value, str) for name, value in mapping.items()
        ):
            raise ValueError(f"MCP server '{server['name']}' in {config_path} has a non-string {key} map: {mapping}")
    if server.get("env_secrets") and not server.get("env_file") and not _all_in_environment(server["env_secrets"]):
        # resolve_secret would raise later with a clearer message, but saying it
        # here names the file that needs the env_file key.
        raise ValueError(
            f"MCP server '{server['name']}' in {config_path} declares env_secrets "
            f"but no env_file, and the named vars are not in the environment"
        )


def _all_in_environment(env_secrets):
    return all(os.environ.get(var) for var in env_secrets.values())


# %%
# Rendering #


def expand_tokens(value, repo_root, repo_parent):
    """
    Replace {repo_root} / {repo_parent} anywhere in a string, list or dict.
    str.replace rather than str.format: command lines legitimately contain
    braces, and a stray one must not raise.
    """
    if isinstance(value, str):
        return value.replace(REPO_ROOT_TOKEN, repo_root).replace(REPO_PARENT_TOKEN, repo_parent)
    if isinstance(value, list):
        return [expand_tokens(item, repo_root, repo_parent) for item in value]
    if isinstance(value, dict):
        return {key: expand_tokens(item, repo_root, repo_parent) for key, item in value.items()}
    return value


def render_server(server, repo_root, repo_parent, redact=False):
    """One declaration -> the mcpServers entry Claude Code reads."""
    rendered = {"command": expand_tokens(server["command"], repo_root, repo_parent)}
    if server.get("args"):
        rendered["args"] = expand_tokens(server["args"], repo_root, repo_parent)
    env = dict(expand_tokens(server.get("env", {}), repo_root, repo_parent))
    for target_var, source_var in (server.get("env_secrets") or {}).items():
        env[target_var] = REDACTED if redact else _resolve_env_secret(server, source_var)
    if env:
        rendered["env"] = env
    return rendered


def _resolve_env_secret(server, source_var):
    """
    Resolve one secret through the shared secret_tools path (real environment
    first, then the declaring repo's env_file) so the config only ever holds the
    NAME of the var, never its value.
    """
    lookup = {
        "name": server["name"],
        "env_file": server.get("env_file"),
        "_base_dir": server["_base_dir"],
        "_var": source_var,
    }
    return resolve_secret(lookup, "_var")


def build_document(servers, repo_root, repo_parent, redact=False):
    """The whole .mcp.json document, servers sorted for a stable diff."""
    return {
        "mcpServers": {
            server["name"]: render_server(server, repo_root, repo_parent, redact=redact)
            for server in sorted(servers, key=lambda server: server["name"])
        }
    }


# %%
# Writing #


def serialize(document):
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def read_existing(dest):
    """The file's current text, or None when it is absent or not a regular file."""
    if not os.path.isfile(dest) or os.path.islink(dest):
        return None
    with open(dest, "r", encoding="utf-8") as handle:
        return handle.read()


def write_document(dest, document):
    """
    Write the document to dest, returning "unchanged", "updated" or "created".

    Two things this must get right. A pre-existing SYMLINK is unlinked rather
    than written through - the dest used to be a managed symlink into the repo,
    and following it would rewrite a tracked file. And the result is chmod 600,
    because a generated document can carry a live API token and the repo file it
    replaced was world-readable.
    """
    text = serialize(document)
    existing = read_existing(dest)
    if existing == text:
        return "unchanged"
    outcome = "updated" if existing is not None else "created"
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.islink(dest):
        os.unlink(dest)
    temporary = f"{dest}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(temporary, 0o600)
    os.replace(temporary, dest)
    return outcome


# %%
