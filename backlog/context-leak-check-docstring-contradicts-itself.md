# context_leak_check's docstring states two policies that cannot both hold

    found:  2026-09-19
    status: open
    verify: sed -n '/personal context/,/forbidden/p' ../src/context_leak_check.py

`src/context_leak_check.py` documents its own rule twice, and the two
statements disagree about the personal repos. One bullet exempts them:

> the personal context's own repos (`personal_credentials`, `personal_dev`,
> any `personal_*` sibling): anything goes; they are the private places that
> know every context by name.

Two bullets later it forbids exactly what it just allowed:

> every other repo (dotfiles **and the personal repos**, public or not):
> every client's identifiers are forbidden.

The code implements the first one. That is almost certainly the intended
policy — `personal_credentials` has to name every context to deploy them, and
its generated deploy map enumerates every client repo by design — so the
second bullet is the stale sentence, not the behaviour.

## Evidence

The check reports `clean across 5 repos` while `personal_dev` and
`personal_credentials` hold hundreds of genuine client identifiers (the
deploy map, the per-machine workspaces, `personal.env`'s Jira settings).
Found while auditing a public-repo edit on 2026-09-19.

## fix

Delete or rewrite the second bullet so the docstring states the exemption
once. No code change.

## blast radius

Documentation only. The risk of leaving it is the opposite of usual: someone
reads the stricter bullet, believes the personal repos are contaminated, and
"fixes" files that are correct — or distrusts a clean result from the check
that is actually authoritative.
