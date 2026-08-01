# %%
# Imports #

import os

# %%
# Secrets #


def resolve_secret(panel, key):
    """
    Look up the env var named by panel[key] (a source/panel mapping): the real
    environment wins, then the mapping's optional ``env_file`` (path relative
    to its ``_base_dir`` config repo - so tokens live in the
    gitignored/private env files, never in the configs themselves).
    """
    var_name = panel[key]
    value = os.environ.get(var_name)
    if value:
        return value
    env_file = panel.get("env_file")
    if env_file:
        env_path = os.path.join(panel["_base_dir"], os.path.expanduser(env_file))
        if not os.path.exists(env_path):
            raise ValueError(f"'{panel['name']}': env_file {env_path} does not exist")
        value = _parse_env_file(env_path).get(var_name)
        if value:
            return value
    raise ValueError(
        f"'{panel['name']}': env var {var_name} is not set"
        + (f" and not found in {panel['env_file']}" if panel.get("env_file") else " (no env_file configured)")
    )


def _parse_env_file(path):
    """KEY=value lines (optional ``export``, quotes stripped); comments and non-kv lines ignored."""
    values = {}
    with open(path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.replace("export ", "", 1).strip()
            value = value.strip().strip("'\"")
            if key:
                values[key] = value
    return values
