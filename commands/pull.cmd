# Repo acquisition ONLY (configs moved to deploy.cmd - one job per command).
# The pulls stay concurrent: repos_pull execs go_apps/git_puller, which fans
# the pulls out in goroutines, and repos_pull_check fans its fetches out the
# same way. Clone check comes after the pulls because the pulls refresh the
# <context>_repos.yaml configs in the *_credentials repos. The env sync comes
# after the clone, where the shells' gitpullall chain puts it, so a fresh
# clone is synced too.
description: pull all repos concurrently, offer missing clones, sync python envs
order: 10
platforms: darwin linux windows
steps:
  repos_pull requires=git
  repos_clone requires=uv
  python_envs_sync requires=uv
