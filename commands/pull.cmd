# Repo acquisition ONLY (configs moved to deploy.cmd - one job per command).
# The pulls stay concurrent: repos_pull execs go_apps/git_puller, which fans
# the pulls out in goroutines, and repos_pull_check fans its fetches out the
# same way. Clone check comes after the pulls because the pulls refresh the
# <context>_repos.yaml configs in the *_credentials repos.
description: pull all repos concurrently, then offer missing clones
order: 10
platforms: darwin linux windows
steps:
  repos_pull requires=git
  repos_clone requires=uv
