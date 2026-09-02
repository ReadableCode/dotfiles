# Gmail filters as code

`src/gmail_filters.py` makes a Gmail account's filters match a yaml file. The
file is the source of truth; Gmail is derived from it. Filters are never edited
in the Gmail UI — `apply` deletes any filter the file does not describe.

## Where the file lives

`<context>_credentials/<context>_gmail_filters.yaml` — the same overlay pattern
as `<context>_googlemail.yaml`, and for the same reason: the filters name real
senders, so they belong in the private credentials repo, never here. The
script finds the file from `--context`, so one context's rules can only ever be
applied through that context's mailbox:

```bash
uv run python src/gmail_filters.py --context personal plan      # diff, no writes
uv run python src/gmail_filters.py --context personal apply     # create / delete / backfill
uv run python src/gmail_filters.py --context personal backfill --only NAME --execute
```

The yaml names its `mailbox:` (an entry in that context's `_googlemail.yaml`,
so auth is the shared `GMAIL_TOKEN_<ACCOUNT>` grant) and its `account:`
address. Before touching anything the script reads Gmail's profile and refuses
if the address differs — a personal file cannot be applied to a work inbox by
pointing it at the wrong mailbox. The token needs `gmail.modify` **and**
`gmail.settings.basic`; filter writes fail with a 403 scope error otherwise.

## What it will and won't do

- Creates labels on demand; never deletes a label.
- Creates filters in the file that Gmail lacks; deletes filters Gmail has that
  the file lacks. Gmail cannot edit a filter, so a changed entry is a delete +
  create and shows as one of each in `plan`.
- Refuses any action that adds `SPAM` or `TRASH`. Nothing it does can delete
  mail: `backfill` uses `batchModify`, whose payload is label ids only.
- Gmail allows **one user label per filter** (`Too many user labels in
  filter`). An entry adding several is expanded into one Gmail filter per user
  label with identical criteria; the extras appear in `plan` as
  `name [+Label]`. System labels (STARRED, IMPORTANT, INBOX, SPAM) don't count.
- `backfill: true` on an entry relabels existing matching mail when that entry
  is (re)created by `apply`; the `backfill` subcommand does the same on demand
  and is a dry-run count unless `--execute` is given. Broad filters can match
  tens of thousands of messages — check the count first.

## Yaml shape

```yaml
mailbox: personal_gmail
account: someone@gmail.com
filters:
  - name: bills            # unique; for humans and plan output only
    criteria:              # Gmail's own keys: from, to, subject, query, negatedQuery, hasAttachment
      query: "from:(a.com OR b.com) subject:(bill OR statement)"
    action:
      add: [STARRED, "!Priority", FinancialLegal/Bills]   # label names; system labels by name
      remove: [SPAM]                                      # never send to spam
    backfill: true
```

Criteria are compared with `filters.list` verbatim — a rule made in the UI
before adoption may carry odd encodings like `{@example.com example}`; keep them
as reported or expect a delete + create.
