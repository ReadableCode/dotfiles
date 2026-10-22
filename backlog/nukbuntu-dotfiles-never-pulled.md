# nukbuntu: the dotfiles checkout is never pulled, so its tools and configs are months old

    found:  2026-10-22
    status: open
    verify: ssh jason@192.168.86.139 'git -C ~/GitHub/dotfiles fetch -q && git -C ~/GitHub/dotfiles status -sb | head -1; git -C ~/GitHub/dotfiles log -1 --format=%cd'

nukbuntu's `~/GitHub/dotfiles` sits at f6e87c7 from 2026-09-02, 256 commits
behind origin. Its only cron pull is `Docker/scripts/git_pull_nukbuntu.sh`,
which fetches the Docker and server_configs repos and nothing else; nothing
runs `gitpullall`, `clone_repos.py` or `deploy_configs.py` there. So every
dotfiles tool is stale on that box: on 2026-10-22
`uv run src/app_removals.py` failed with "No such file or directory" because
the script postdates the checkout.

`docs/homelab_deployments.md` also says nukbuntu has "no user or root crontab
at all", which is wrong: jason's crontab has the `*/5` git_pull_nukbuntu.sh
line and a Monday 10:30 prune of the behemoth flash backups.

Evidence, 2026-10-22:

    ## master...origin/master [behind 256]
    */5 * * * * bash /home/jason/GitHub/Docker/scripts/git_pull_nukbuntu.sh >> ...
    30 10 * * 1 ls -t /home/jason/docker_app_data/backups/behemoth_flash/*.zip ... | xargs -r rm

## fix

Give nukbuntu the same dotfiles loop elitedesk has (`jason.cron`, minute 5 of
every quarter hour: `clone_repos.py --yes` then `deploy_configs.py deploy`),
declared in a repo-tracked crontab for nukbuntu the way elitedesk's is, and
correct the crontab line in `docs/homelab_deployments.md`. One-off catch-up
until then:

    ssh jason@192.168.86.139 'git -C ~/GitHub/dotfiles pull --ff-only'

## blast radius

The first deploy after the catch-up applies two months of config changes to
nukbuntu at once (shell configs, links, removals); `deploy_configs.py deploy
--dry-run` first shows them.

## not doing yet

Which repo should own nukbuntu's crontab (server_configs holds elitedesk's,
but nukbuntu's current line was installed by hand from the Docker README's
bootstrap) is a decision, and the first deploy should be read before it runs.
