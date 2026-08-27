# Config deployment ONLY (repo pulling lives in pull.cmd). Deploy before
# prune: prune only removes what the removals files name AND no live manifest
# entry wants, so it is safe after a deploy (see docs/deploy_configs.md).
description: deploy configs to this machine, then prune removed ones
order: 20
platforms: darwin linux windows
steps:
  configs_deploy requires=uv
  configs_prune requires=uv
