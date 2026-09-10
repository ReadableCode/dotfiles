# lint: flake8 is red at HEAD, so the documented lint gate cannot be used

    found:  2026-09-09
    status: open
    verify: cd ~/GitHub/dotfiles && uv run flake8 src/ tests/; echo "exit=$?"

`CLAUDE.md` documents `uv run flake8 .` as the lint command, but it exits 1 on
a clean checkout of master (`2908c2f`). 15 violations in four files, none of
them touched by the 2026-09-09 disk-cleanup work that surfaced this — verified
by `git status --short` reporting all four unmodified while the failures
reproduced.

## Evidence

```
$ uv run flake8 src/ tests/
src/context_leak_check.py:150:121: E501 line too long (129 > 120 characters)
src/context_leak_check.py:242:121: E501 line too long (129 > 120 characters)
src/context_leak_check.py:318:121: E501 line too long (126 > 120 characters)
src/context_leak_check.py:394:121: E501 line too long (125 > 120 characters)
tests/test_context_leak_check.py:31:121: E501 line too long (130 > 120 characters)
tests/test_context_leak_check.py:38:121: E501 line too long (158 > 120 characters)
tests/test_context_leak_check.py:55:121: E501 line too long (146 > 120 characters)
tests/test_context_leak_check.py:100:121: E501 line too long (126 > 120 characters)
tests/test_deploy_map.py:114:56: E128 continuation line under-indented for visual indent
tests/test_deploy_map.py:337:5: E731 do not assign a lambda expression, use a def
tests/test_deploy_map.py:383:121: E501 line too long (131 > 120 characters)
tests/test_deploy_map.py:387:5: E731 do not assign a lambda expression, use a def
tests/test_deploy_map.py:387:121: E501 line too long (166 > 120 characters)
tests/test_init_worktree.py:290:121: E501 line too long (121 > 120 characters)
tests/test_init_worktree.py:302:121: E501 line too long (121 > 120 characters)
exit=1
```

`uv run pytest` is green (404 passed), so this is lint only, not broken code.

## fix

13 of the 15 are E501 on lines that are long because they hold identifier
strings and assertion messages. Wrap them; do not raise `max-line-length` in
`.flake8` and do not add `# noqa`.

```bash
cd ~/GitHub/dotfiles
$EDITOR src/context_leak_check.py        # 150, 242, 318, 394
$EDITOR tests/test_context_leak_check.py # 31, 38, 55, 100
$EDITOR tests/test_deploy_map.py         # 114 (E128), 337 + 387 (E731 -> def), 383, 387
$EDITOR tests/test_init_worktree.py      # 290, 302
uv run flake8 src/ tests/ && uv run isort . && uv run pytest -q
```

The two E731s want the lambdas turned into `def`s, not reformatted.

## blast radius

None at runtime. Every change is whitespace, line wrapping, or a lambda
becoming a `def` inside a test. `src/context_leak_check.py` is also deployed
as the pre-commit hook in the client checkouts, so re-run
`uv run python src/context_leak_check.py` afterwards to confirm it still
reports clean across all repos.

## not doing yet

Deferred because it surfaced during unrelated disk-cleanup work and fixing it
would have mixed a lint sweep into that commit. Nothing needs deciding first —
this is straightforward once someone wants the lint gate green. Worth doing
before anything starts enforcing flake8 in CI or a pre-commit hook, because
until then every run is red for reasons unrelated to the change under review.
