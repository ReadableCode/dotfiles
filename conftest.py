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

And it points ``config.grandparent_dir``, the folder every tool searches for the
other repos (credentials, dev and overlay repos), at an empty temp folder before
any module copies it. No test reads the real repos cloned next to this checkout,
so the suite runs the same from the main checkout, a T3 worktree or a bare
export. A test that needs sibling repos builds fake ones and points its module
at them (``overlay_tree`` in ``test_deploy_configs.py``).
"""

import atexit
import os
import shutil
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_UTILS_DIR = os.path.join(ROOT_DIR, "tests", "test_utils")
SRC_DIR = os.path.join(ROOT_DIR, "src")

for _path in (ROOT_DIR, TEST_UTILS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]

import config  # noqa: E402

SIBLINGS_DIR = tempfile.mkdtemp(prefix="dotfiles_tests_siblings_")
atexit.register(shutil.rmtree, SIBLINGS_DIR, ignore_errors=True)
config.grandparent_dir = SIBLINGS_DIR
