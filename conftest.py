"""Pytest bootstrap for the unit suite (``tests/``).

pytest imports the repo-root ``conftest.py`` for any test session, so putting the
import-path setup here means individual test files no longer have to manipulate
``sys.path`` themselves. It makes the first-party packages importable:

* the repo root, so ``from src.utils... import ...`` resolves
* ``tests/test_utils``, so the shared ``config_test_utils`` helper resolves
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_UTILS_DIR = os.path.join(ROOT_DIR, "tests", "test_utils")

for _path in (ROOT_DIR, TEST_UTILS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)
