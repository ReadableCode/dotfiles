# Running `# %%` cells in JupyterLab from T3 (tried 2026-10-16, not adopted)

The idea: instead of VS Code's Interactive Window, run a `.py` file's `# %%`
cells in JupyterLab on the agent's host, opened in T3 Code's built-in browser,
with jupytext opening the `.py` as a notebook and saving it back as plain
`py:percent`. It worked, and it was dropped in favour of VS Code. Nothing is
installed, deployed or wrapped by a command; this page is the record so the
trial never has to be repeated from scratch.

The launcher that was built and tested, `src/jupyter_lab.py` with its tests and
the `init_worktree.teardown` hook, is in commit `81936db` and was removed in the
commit after it. `git show 81936db` has all of it; `git revert` of the removal
brings it back.

## The manual recipe

From the repo root, in the project's own environment, adding nothing to it:

```bash
uv run --with jupyterlab --with jupytext jupyter lab --no-browser --ip 127.0.0.1 --port 8888
```

Then right-click a `.py` -> **Open With -> Jupytext Notebook**; Shift+Enter runs
a cell. For saves with no YAML header and no cell metadata the repo needs:

```toml
[tool.jupytext]
formats = "py:percent"
notebook_metadata_filter = "-all"
cell_metadata_filter = "-all"
```

The shells already carry an older `startjupyterlab` alias
(`application_configs/bash/.bash_aliases`, `powershell_aliases.ps1`): it runs
whatever `jupyter` is on PATH from `$gitDir` on `0.0.0.0:8181`, with neither the
project environment, jupytext nor a loopback bind. It was not changed.

Verified: a save after running cells, including one that raised, changed only
the cells typed by hand. No outputs, no header.

## What was learned

- **Kernel name.** The venv is never listed by name. The `Python 3 (ipykernel)`
  kernel runs in uv's overlay environment, whose imports resolve to the
  project's `.venv`. Checked with `sys.executable` and `pandas.__file__`.
- **No token printed** when `~/.jupyter/jupyter_server_config.json` sets
  `ServerApp.password`: a password turns token auth off. Passing
  `--IdentityProvider.token=<t> --PasswordIdentityProvider.hashed_password=
  --ServerApp.password=` on the command line overrides it (403 without the
  token, 200 with it). The `/lab?token=` URL logs T3's browser in, and the
  cookie stays in its default profile.
- **Port drift.** Jupyter moves to 8889 and up when 8888 is taken, so a saved
  URL can point at someone else's server; `--ServerApp.port_retries=0` makes it
  fail instead. A stopped server leaves TIME_WAIT sockets that block a plain
  bind probe but not the server, which binds with `SO_REUSEADDR`; a free-port
  probe has to set it too.
- **Checkpoints out of the repo.** `--FileCheckpoints.root_dir=<dir>` moves
  `.ipynb_checkpoints/` to a mirror tree outside the checkout (it applies to
  the async subclass the jupytext contents manager uses).
- **Global jupytext config.** Without a repo config, jupytext reads
  `~/.config/jupytext/jupytext.toml`. A `pyproject.toml` with no
  `[tool.jupytext]` does not stop that search. `formats = "py:percent"`
  matches `.py` only, so `.ipynb` files are unaffected.
- **Theme.** A hand-placed
  `~/.jupyter/lab/user-settings/@jupyterlab/apputils-extension/themes.jupyterlab-settings`
  outranks any default, and was what made it white. jupyterlab_server saves
  settings with a plain `open(path, "w")`, so a symlinked settings file is
  written through, not replaced.
- **Lifetime.** A server started from Claude's background Bash dies at the
  30-minute background-task limit. Detaching it (`start_new_session=True`)
  fixes that. Stopping it when its T3 thread settles did **not** work: settling
  leaves the thread's Claude session alive with status `ready`, and a verdict
  that ranks a live session above settled never sees `settled`. A fix would
  read `settledAt`, `settledOverride` and `deleted_at` alone. Stopping when the
  checkout was deleted did work (13 s).
- **Finding the thread from inside a session.** `CLAUDE_CODE_SESSION_ID`
  equals `nativeThreadRef.nativeId` in the `payload_json` of
  `orchestration_v2_projection_provider_threads` in T3's `statev2.sqlite`.

## From the earlier note on this trial (not re-verified)

- In a remote environment's tab, open the page with the **⋮** menu, **Open in
  <environment>'s browser**, since desktop tabs run on the local machine.
- On Ubuntu 23.10 and later the host browser needs a one-time
  `sudo <host's t3> browser setup` to install the
  `/etc/apparmor.d/t3-chrome-headless-shell` profile.
- The host browser keeps its own persistent profile. Cookie import is
  desktop-only, so the first sign-in is by hand.
- Open questions it never answered: whether the streamed browser is responsive
  over a travel connection, and whether the notebook view beats Shift+Enter in
  a `.py` file.
