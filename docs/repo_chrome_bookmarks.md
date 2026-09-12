# Chrome bookmarks as a repo file

`src/chrome_bookmarks.py` saves the personal Chrome profile's bookmarks into
`personal_credentials/bookmarks/` and collapses the duplication Chrome Sync
creates. The repo copy is the source of truth; Chrome is rebuilt from it.

## Why this exists

When a machine reconnects to Chrome Sync after being offline for long enough,
Sync reconciles the server tree against the local one and keeps both: every
top-level folder appears twice, and from then on new bookmarks land in one
copy or the other. It happened 2026-08 and again 2026-09. Fixing it by hand
means reading two trees side by side; the script does it in one pass.

## Where things live

| Path | What |
|------|------|
| `personal_credentials/bookmarks/personal_bookmarks.json` | the deduped tree in Chrome's own order, only `name`, `url`, `type`, `date_added` and `children` per node; edit this |
| `personal_credentials/bookmarks/personal_bookmarks.html` | Netscape import file generated from the JSON; never edit |
| `personal_credentials/bookmarks/Bookmarks-organized.md` | the cleanup write-up: what was collapsed, what was judged stale |

Bookmarks are synced, so there is one file, not one per host. Only the
personal profile (`Default`) is handled; client profiles keep their own.

## The cycle

1. Export and dedupe from the live profile:

   ```bash
   uv run python src/chrome_bookmarks.py
   ```

   Reads Chrome's `Bookmarks` file for the `Default` profile, merges same-name
   sibling folders (recursively, keeping additions made to either copy), drops
   a url repeated inside one folder, prints every merge and drop, and writes
   both repo files. On macOS the terminal needs Full Disk Access to read the
   Chrome profile folder.

   The JSON is deterministic: Chrome's `guid`, `id`, `date_modified`,
   `date_last_used`, `meta_info`, `checksum` and `sync_metadata` are dropped
   (they change on every sync and differ between the duplicate copies), keys
   are sorted, indent is Chrome's three spaces, and bookmark order is
   Chrome's, never alphabetical. Re-running on an unchanged tree reproduces
   the file byte for byte, so a diff shows only bookmarks added, removed or
   moved.

2. Edit `personal_bookmarks.json` if anything needs deciding: stale items that
   a reconnecting device brought back, a url bookmarked loose on the bar that
   already lives in a folder. Then regenerate the HTML from the edited copy:

   ```bash
   uv run python src/chrome_bookmarks.py --input ../personal_credentials/bookmarks/personal_bookmarks.json
   ```

3. Commit both files in `personal_credentials`.

4. In Chrome's Bookmark Manager on the personal profile, delete everything in
   the Bookmarks bar, Other bookmarks and Mobile bookmarks, then import the
   HTML (three-dot menu, Import bookmarks). The bar folder is flagged
   `PERSONAL_TOOLBAR_FOLDER` so it lands on the bar; anything from the other
   roots lands in Other bookmarks.

Import goes through the bookmarks API, so Sync treats it as real edits and
pushes them to every device. Replacing the on-disk `Bookmarks` file does not
survive Sync: the server copy wins on next launch. Deleting first matters
too: Chrome imports into an `Imported` folder whenever the bar already has
content.

## What the merge will not decide

- A url that legitimately lives in two folders stays in both; only repeats
  inside the same folder are dropped.
- Items in Other bookmarks and Mobile bookmarks are kept in the JSON. The
  2026-08 cleanup emptied both roots on purpose; when a device brings the old
  contents back, remove them from the JSON before step 2.
- Nothing is deleted from Chrome by the script. The delete-then-import in
  step 4 is the only write, and it is done by hand in the Bookmark Manager.
