# Formatting

## Flake8

- To list and count the formatting issues with flake8:

  ```bash
  (flake8 | grep './' | head -n 20) 2>/dev/null && flake8 | grep './' | wc -l
  ```

  - To auto format with flake8:

    ```bash
    flake8 --ignore=E501,W503 --max-line-length=88 --exclude=src/proto
    ```

## Black

- To list and count the formatting issues with black:
  
  - To list changes black would make:

      ```bash
      black --check .
      ```

  - To auto format with black:

      ```bash
      black .
      ```

## Isort

- To list and count the formatting issues with isort:

  - To list changes isort would make:
  
    ```bash
    isort --profile black --check-only .
    ```
  
  - To auto format with isort:
  
    ```bash
    isort --profile black .
    ```

## MyPy

- To list and count the formatting issues with mypy:

  - Must be run from Project root directory on src directory

  - To see what changes need to be made:
  
    ```bash
    mypy src/.
    ```

  - To auto format with mypy:

    ```bash
    mypy src/. --strict
    ```

## Running precommit

- Install
  
    ```bash
    pre-commit install
    ```

- Run

  - To auto format with pre-commit:
  
    ```bash
    pre-commit run --all-files
    ```

## Git hooks in this repo

Two hooks, deployed by the personal_dev overlay as symlinks into
`.git/hooks/` (hooks are untracked, so they need a manifest entry):

| Hook | Payload | Runs |
| --- | --- | --- |
| `pre-commit` | `application_configs/git/hooks/pre-commit.context-leak` | `src/context_leak_check.py --staged` |
| `pre-push` | `application_configs/git/hooks/pre-push.dotfiles-checks` | `isort --check-only .`, `flake8 .`, `mypy .`, `pytest -q` |

The split is deliberate. A leaked client identifier must never enter history at
all, so that check has to be the earlier one. Formatting is the opposite trade:
a local commit stays cheap, but nothing should reach the remote needing a
follow-up "fix lint" commit, which is what happened when a 122-character line
sat on `master` for a day in September 2026.

`pre-push` runs this repo's own uv-pinned tools, the same four commands
CLAUDE.md documents. It deliberately does **not** use the `pre-commit`
framework: that would pin a second set of linter versions beside
`pyproject.toml` and `uv.lock`, and would pull in a formatter this repo does not
use. Both hooks fail closed - a missing `uv` is a refused push, never a silent
skip.

A push that only deletes remote branches skips the checks (nothing new is going
out). `git push --no-verify` is the escape hatch.
