"""Collect host metrics with GET requests only; no notifications or remote commands."""
from django.core.management.base import BaseCommand, CommandError

from portal.monitoring import MonitoringError, collect_host, host_configs, write_snapshot


class Command(BaseCommand):
    help = "Save a read-only Proxmox monitoring snapshot. Does not alter VMs or send notifications."

    def handle(self, *args, **options):
        try:
            configs = host_configs()
            if not configs:
                raise MonitoringError("No monitoring hosts configured. Set MONITORING_HOSTS_JSON first.")
            hosts = [collect_host(config) for config in configs]
            write_snapshot(hosts)
        except MonitoringError as exc:
            raise CommandError(str(exc)) from None
        for host in hosts:
            self.stdout.write(f"{host['name']}: {host['state']}")
        if any(host["state"] != "connected" for host in hosts):
            raise CommandError("Snapshot saved with unavailable or partial checks. Review read-only access.")
