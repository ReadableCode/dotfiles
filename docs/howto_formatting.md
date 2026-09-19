# Formatting

Two tools, all configured in `pyproject.toml`. There is no `.flake8`, no
`.isort.cfg` and no `.pre-commit-config.yaml` in this repo.

## Ruff

`ruff` is both the formatter and the linter, and replaced `flake8` + `isort` on
2026-09-19. It also replaced `.flake8`, `.isort.cfg` and a `[tool.flake8]`
block that flake8 never read (it has no pyproject support). The old
`.isort.cfg` additionally carried ten `known_third_party` names copied from a
work repo - `brand_tools`, `concur_schemas`, `ap_vendor_split_hc_us` and
friends - none of which have ever existed here.

```bash
uv run ruff format .          # apply the formatter
uv run ruff format --check .  # report only
uv run ruff check --fix .     # lint + import sorting, fixing what it can
uv run ruff check .           # report only
```

Config, all under `[tool.ruff]`:

| Setting | Value | Was |
| --- | --- | --- |
| `line-length` | 120 | `.flake8 max-line-length` |
| `lint.select` | `E`, `W`, `F`, `C90`, `I` | flake8's default set plus isort |
| `lint.ignore` | `E203` | `.flake8 extend-ignore` (`W503` has no ruff equivalent) |
| `lint.mccabe.max-complexity` | 15 | `.flake8 max-complexity` |

`ruff format` is black-compatible. This repo did not previously run a
formatter, so adopting it reformatted 38 files in one commit.

## Format on save (this folder only)

`.vscode/settings.json` in this repo points the Python formatter at ruff and
turns the flake8 extension off, because this repo's venv no longer has flake8.

It is **folder-scoped on purpose and must stay that way.** The user-level
settings (`personal_credentials/vscode/settings.json`) keep black + isort +
flake8 as the Python stack for every folder, and sibling repos depend on that:
they pin those tools in their own venvs and their own `.pre-commit-config.yaml`,
and at least one carries its own tracked `.vscode/settings.json` asserting black
and explicitly turning ruff's code actions off. Changing the user-level file
would reformat those repos with the wrong tool.

Only resource-scoped settings can be overridden per folder.
`ruff.importStrategy` is **window**-scoped, so it is deliberately absent here -
setting it anywhere would reach every repo, and a sibling whose venv has no ruff
would start erroring on every file. `ruff.path` is resource-scoped and uses the
same `["${interpreter}", "-m", "ruff"]` contract the user-level file uses for
black, isort and flake8, so the version is the one `uv.lock` pins.

## MyPy

Ruff does not type-check, so mypy stays. `ignore_missing_imports = true` and
`show_error_codes = true` in `pyproject.toml`.

```bash
uv run mypy .
```

## Tests

```bash
uv run pytest
```

Fast unit tests only, no external deps or credentials, so a plain run is always
safe.

## Git hooks in this repo

Two hooks, deployed by the personal_dev overlay as symlinks into `.git/hooks/`
(hooks are untracked, so they need a manifest entry):

| Hook | Payload | Runs |
| --- | --- | --- |
| `pre-commit` | `application_configs/git/hooks/pre-commit.context-leak` | `src/context_leak_check.py --staged` |
| `pre-push` | `application_configs/git/hooks/pre-push.dotfiles-checks` | `ruff format --check .`, `ruff check .`, `mypy .`, `pytest -q` |

The split is deliberate. A leaked client identifier must never enter history at
all, so that check has to be the earlier one. Formatting is the opposite trade:
a local commit stays cheap, but nothing should reach the remote needing a
follow-up "fix lint" commit, which is what happened when a 122-character line
sat on `master` for a day in September 2026.

`pre-push` runs the `--check` forms and never rewrites files. Fixing during a
push would leave the corrected versions *outside* the commits being pushed, so
the unformatted code would go out anyway and leave a dirty tree behind. When it
fails it prints the one command that fixes it:

```bash
uv run ruff format . && uv run ruff check --fix .
```

Both hooks fail closed - a missing `uv` is a refused push, never a silent skip.
A push that only deletes remote branches skips the checks. `git push
--no-verify` is the escape hatch.
