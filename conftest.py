"""Pytest bootstrap for the unit suite (``tests/``).

pytest imports the repo-root ``conftest.py`` for any test session, so putting the
import-path setup here means individual test files no longer have to manipulate
``sys.path`` themselves. It makes the first-party packages importable:

* the repo root, so ``from src.utils... import ...`` resolves
* ``tests/test_utils``, so the shared ``config_test_utils`` helper resolves

It also drops every ``GIT_*`` variable before any test runs. A git hook started
from a linked worktree inherits an absolute ``GIT_DIR`` naming the real repo, so
the tests that build throwaway repos (``git init --bare``, ``git worktree add``,
``git commit``) wrote into it instead: on 2026-10-23 a pre-push from a T3
worktree set ``core.bare = true`` in the main checkout and moved its branch.
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_UTILS_DIR = os.path.join(ROOT_DIR, "tests", "test_utils")

for _path in (ROOT_DIR, TEST_UTILS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]
