# Find Artifacts of Syncing Issues

## Find Files on Linux

* Find empty folders and show them

    ```bash
    find . -type d -empty
    ```

* Find empty folders and delete them

    ```bash
    find . -type d -empty -delete
    ```

## Files with like "NJ_NJ -" in their name

* Find Them:

    ```bash
    find . -regextype posix-extended -regex '.*[[:upper:]][[:upper:]]_[[:upper:]][[:upper:]]\s-\s.*' -type f
    ```

* Delete Them:

    ```bash
    find . -regextype posix-extended -regex '.*[[:upper:]][[:upper:]]_[[:upper:]][[:upper:]]\s-\s.*' -type f -delete
    ```

## Files with (#) in their name or (##) in their name

* Find Them:

    ```bash
    find . -regextype posix-extended -regex '.*\([[:digit:]][[:digit:]]\).*' -type f
    ```

* Delete Them:

    ```bash
    find . -regextype posix-extended -regex '.*\([[:digit:]][[:digit:]]\).*' -type f -delete
    ```

## Directories with (#) in their name

* Find Them:

    ```bash
    find . -regextype posix-extended -regex '.*\([[:digit:]]\).*' -type d
    ```

* Delete Them:

    ```bash
    find . -regextype posix-extended -regex '.*\([[:digit:]]\).*' -type d -delete
    ```

## find files by search name

* Find Them:

  * on linux

    ```bash
    find . -name "*search_name*"
    ```

  * on windows

    ```bash
    Get-ChildItem -Recurse -ErrorAction SilentlyContinue -Filter "search_name" | Select-Object FullName
    ```

* Delete Them:

  * on linux

    ```bash
    find . -name "*search_name*" -delete
    ```

  * on windows

    ```bash
    Get-ChildItem -Recurse -ErrorAction SilentlyContinue -Filter "search_name" | Remove-Item
    ```

## find files with "sync" in their name

* Find Them:

    ```bash
    find . -name "*sync*"
    ```

* Delete Them:

    ```bash
    find . -name "*sync*" -delete
    ```

## find files with "sync_conflict" or "syncthing" in them

* Find Them:

    ```bash
    find . \( -name "*sync-conflict*" -o -name "*~syncthing*" \)
    ```

* Delete Them:

    ```bash
    find . \( -name "*sync-conflict*" -o -name "*~syncthing*" \) -delete
    ```

## find empty README.md files

* Find Them:

    ```bash
    find . -type f -name 'README.md' -exec bash -c 'for f; do if [ ! -s "$f" ] || ! grep -q "[^[:space:]]" "$f"; then echo "$f"; fi; done' bash {} +
    ```

* Delete Them:

    ```bash
    find . -type f -name 'README.md' -exec bash -c 'for f; do if [ ! -s "$f" ] || ! grep -q "[^[:space:]]" "$f"; then rm -f "$f"; fi; done' bash {} +
    ```

## find file and directories with a specefic file path part

* Find Them:

    ```bash
    find . -type d \( -path "*/.git/refs/remotes/origin/patch*" -o -path "*/.git/refs/remotes/origin/minor*" \)
    ```

* Delete Them:

    ```bash
    find . -type d \( -path "*/.git/refs/remotes/origin/patch*" -o -path "*/.git/refs/remotes/origin/minor*" \) -exec rm -rf {} +
    ```

## finding large files with ls

* Find Them:

    ```bash
    ls -lSh
    ```

  * head only

    ```bash
    ls -lSh | head
    ```
