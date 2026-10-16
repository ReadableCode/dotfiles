# python cells: the JupyterLab + jupytext workflow in T3 has no install method

    found:  2026-10-16
    status: open
    verify: grep -rn -i -E 'jupytext|jupyterlab' ~/GitHub/dotfiles/docs ~/GitHub/dotfiles/app_lists ~/GitHub/dotfiles/scripts

On 2026-10-16 a trial started that replaces VS Code's `# %%` Interactive
Window with JupyterLab running on the agent's host. JupyterLab is opened in that
T3 environment's browser tab (`localhost:8888`), and jupytext opens `.py` files
in the percent format as notebooks. The trial runs on a client box, ad hoc:
`uv run --with jupyterlab --with jupytext jupyter lab`, plus a `[tool.jupytext]`
block added by hand to that one repo's `pyproject.toml`. Nothing in dotfiles
records it, so the next machine has no way to reproduce it.

**Evidence:** the `verify:` grep returns nothing. The trial's steps exist only
in the T3 thread that ran them.

**fix**, if the trial is kept:

1. Pick one install method and use only that one. Either:
   - a `jupyterlab` + `jupytext` dev dependency in each Python repo's `pyproject.toml`, or
   - a `uv run --with ...` launcher documented in dotfiles.

   Grep first for any existing Jupyter install method, so this doesn't add a second.
2. Add this block to each Python repo that uses `# %%` cells, so that saving
   writes only code and markers, with no outputs and no metadata header:

   ```toml
   [tool.jupytext]
   formats = "py:percent"
   notebook_metadata_filter = "-all"
   cell_metadata_filter = "-all"
   ```

3. Document the workflow in `docs/setup_t3_code.md`:
   - start the server on the host, bound to `127.0.0.1`;
   - in a remote environment's tab, use the **⋮** menu, **Open in <environment>'s browser**, because desktop tabs run on the local machine;
   - on Ubuntu 23.10 and later, run `sudo <host's t3> browser setup` once to install the `/etc/apparmor.d/t3-chrome-headless-shell` profile;
   - the host browser keeps its own persistent profile. Cookie import is desktop-only, so the first time, sign in by hand.

**blast radius:** for each repo, either a dev-group dependency or a
`pyproject` block. The AppArmor profile changes a host, but that's a one-time
change made by the user, not by an agent.

**not doing yet:** this waits on the trial. It is unproven whether the
streamed browser is responsive over a travel connection, and whether
JupyterLab's notebook view can replace pressing Shift+Enter in a `.py` file.
