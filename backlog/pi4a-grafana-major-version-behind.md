# raspberrypi4a: grafana is two major versions behind and the upgrade is not automatic

    found:  2026-09-19
    status: open
    verify: ssh pi@192.168.86.22 'apt-cache policy grafana'

raspberrypi4a runs grafana **12.1.1** while the repo now offers **13.2.2**. It
sat still because that Pi's grafana apt source had an expired signing key
(`EXPKEYSIG 963FA27710458545`) and fetched nothing at all; the source was
migrated to `apt.grafana.com` with a current key on 2026-09-19, which is what
exposed the gap.

## Evidence

    grafana    installed=12.1.1 candidate=13.2.2

## fix

    ssh pi@192.168.86.22 'sudo apt-get install -y grafana && systemctl status grafana-server --no-pager'

## blast radius

Real, which is why it is here and not just done. A grafana major version jump
can migrate the dashboard database irreversibly and can drop plugins that have
not been rebuilt. Take a copy of `/var/lib/grafana/grafana.db` first. Check
what actually depends on this instance before upgrading — elitedesk also runs
grafana as a compose service in the Docker repo, so this Pi's instance may be
redundant, in which case removing it is the better answer than upgrading it.

## not doing yet

Needs the decision above: upgrade, or retire this instance in favour of the
elitedesk one. Neither is urgent, and 12.1.1 is running fine.
