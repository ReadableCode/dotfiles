# String Replacement with VSCode

## Replacing substrings

- Replace `## Something ##` with `# Something #` in all files in the current directory:

  1. Open the search and replace panel (`Ctrl+Shift+F`).
  2. Enable the regular expression mode by clicking the `.*` button.
  3. Enter `^## (.*?) ##` in the search field.
  4. Enter `.py` in files to include field.
  5. Verify that the replacements look correct
  6. Click the `Replace All` button.
