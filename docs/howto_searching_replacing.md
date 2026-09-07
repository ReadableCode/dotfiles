# Replacements

To replace lines with a pattern like:

```bash
    comment: "The report country"
```

Use the following command:

```bash
^\s{4}comment:.*\n?
```

To replace lines with a pattern like:

```bash
\n    type: 
```

Use the following command:

```bash
\n\s{4}type
```

To replace lines with a pattern like:

```bash
      \ *\n
```

Use the following command:

```bash
^\s{6}\ *\n
```
