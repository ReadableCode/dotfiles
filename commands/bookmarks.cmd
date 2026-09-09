# Chrome bookmarks export (src/chrome_bookmarks.py): apply rewrites the
# repo copy in personal_credentials/bookmarks from the live profile; the
# check exports to a scratch dir and diffs against the repo copy, so drift
# means Chrome has bookmarks the repo does not. Personal machines only in
# practice: the step skips itself when the personal credentials repo is not
# cloned here.
description: chrome bookmarks - export the personal profile into the credentials repo
order: 230
platforms: darwin linux windows
steps:
  bookmarks_export requires=uv
