# Integration tests (manual)

These are **not** unit tests. They verify that an external integration is set up
correctly **on the machine you run them from** — they send real emails, read and
write live Google Sheets, and create/read/write real S3 buckets. They are *not*
collected by a default `pytest` run (see `testpaths` in `pyproject.toml`); a
developer runs them by hand after configuring credentials.

## Prerequisites

These require live credentials, so they only pass on a machine that is actually
configured for the service under test:

| File | What it checks | Needs |
|------|----------------|-------|
| `test_gmail_tools.py` | Gmail API send/search/attachment | Google OAuth creds + `.env` with `EMAIL_ADDRESS_FOR_TESTING` |
| `test_google_tools.py` | Google Sheets read/write | Google Sheets/Drive credentials, a `TestApp` workbook |
| `test_s3_tools.py` | S3 upload/download/list | AWS credentials with access to the target bucket |

Put secrets in a `.env` at the repo root (gitignored). Without valid
credentials these will fail on auth — that failure is the test doing its job
(telling you the integration is not set up), not a code bug.

## Running

From the repo root:

```bash
uv run pytest integration_tests/                       # all setup checks
uv run pytest integration_tests/test_gmail_tools.py    # just one

# each file is also runnable directly as a script
uv run python integration_tests/test_s3_tools.py
```
