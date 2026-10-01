# context_leak_check: a public repo may name the user's home town, and nothing refuses it

    found:  2026-09-30
    status: open
    verify: ls ../*_credentials/*_private_places.txt 2>/dev/null || echo "no private places list"

On 2026-09-30 the verify line printed `no private places list`.

`src/context_leak_check.py` refuses one context's identifiers inside another
context's repo. It has no notion of a private place: the user's city,
subdivision, street, zip code or a local business that serves one town. A
public repo in the personal context is exempt from every rule
(`forbidden_for` returns `{}` for `personal_*` checkouts and treats every
other personal repo as owned by no context), so nothing stops a commit that
names the town.

## Evidence

Found on 2026-09-30 in a public personal repo, a finance app: the city
utility's name in a docstring example and a test parametrisation, and a real
grocery store number with its city in three transaction fixtures. All four had
been committed on 2026-08-03 and were fixed by hand the day they were found.
The same day's backlog drafts had named the city, the subdivision's HOA and two
local contractors before they were rewritten with generic slugs.

The checker's identifier lists are derived from `<context>_credentials`, and
the personal context declares none of these places anywhere. No list, no
rule.

## fix

1. Add `personal_credentials/personal_private_places.txt`, one term per line,
   in the shape `_identifiers.txt` already has: the city, the subdivision, the
   street, the zip code, and each local business that serves one town.
2. In `context_leak_check.py`, load that file for the personal context and
   forbid its terms in every repo that is public: `dotfiles`, and any personal
   repo whose remote is a public GitHub repo. Visibility is not derivable
   offline, so list the public repos in `personal_credentials/personal_repos.yaml`
   with a `public: true` key and read that.
3. Add a test beside the existing ones: a public repo containing a listed
   place fails, a private one passes.

## blast radius

Additive. The hook already runs on commit in every repo it covers; a new
term only adds hits. The first run over the public repos will report whatever
is already there, which is the point.

## not doing yet

The `public:` key is a change to the repos declaration that
`clone_repos.py` and the deploy map also read; check that neither rejects an
unknown key before adding it. Which repos are public was checked by hand on
2026-09-30 (`dotfiles` and the finance app are; three others that name the
town are private).
