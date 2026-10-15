"""Read-only Proxmox collection and a deliberately narrow saved-snapshot contract."""
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings

MAX_SNAPSHOT_BYTES = 2_000_000
ERROR_CODES = {"CREDENTIALS_MISSING", "TLS_CONFIGURATION_INVALID", "ACCESS_DENIED",
               "API_UNAVAILABLE", "RESPONSE_TOO_LARGE", "INVALID_RESPONSE",
               "TLS_VERIFICATION_FAILED", "CONNECTION_FAILED"}


class MonitoringError(Exception):
    pass


def number(value, default=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        if not math.isfinite(value):
            return default
    except OverflowError:
        return default
    return value if value >= 0 else default


def label(value, limit=100):
    return str(value or "")[:limit]


def percent(used, total):
    used, total = number(used), number(total)
    if used is None or total is None or total == 0:
        return None
    return round(min(100, used / total * 100), 1)


def size(value):
    value = number(value)
    if value is None:
        return "Unavailable"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def stamp(value):
    value = number(value)
    return value if value is not None and value < 253402300799 else None


def date(value):
    value = stamp(value)
    return datetime.fromtimestamp(value, datetime_timezone.utc) if value is not None else None


def host_configs():
    try:
        configs = json.loads(settings.MONITORING_HOSTS_JSON or "[]")
    except (TypeError, ValueError):
        raise MonitoringError("Invalid monitoring host configuration.") from None
    if not isinstance(configs, list) or len(configs) > 8:
        raise MonitoringError("Configure at most eight monitoring hosts.")
    seen = set()
    for config in configs:
        if not isinstance(config, dict):
            raise MonitoringError("Invalid monitoring host configuration.")
        for key in ("name", "node", "url", "token_id_env", "token_secret_env"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise MonitoringError("Incomplete monitoring host configuration.")
        if config["name"] in seen or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", config["node"]):
            raise MonitoringError("Invalid or duplicate monitoring host.")
        seen.add(config["name"])
        try:
            parsed = urlsplit(config["url"])
        except ValueError:
            raise MonitoringError("Invalid monitoring HTTPS origin.") from None
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise MonitoringError("Monitoring requires an HTTPS origin without embedded credentials.")
        for key in ("token_id_env", "token_secret_env"):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,99}", config[key]):
                raise MonitoringError("Invalid monitoring credential variable name.")
    return configs


class ProxmoxReader:
    def __init__(self, config):
        token_id = os.getenv(config["token_id_env"], "")
        token_secret = os.getenv(config["token_secret_env"], "")
        if not token_id or not token_secret or any(c in token_id + token_secret for c in "\r\n"):
            raise MonitoringError("CREDENTIALS_MISSING")
        self.base = config["url"].rstrip("/") + "/api2/json"
        self.verify = config.get("ca_bundle") or True
        if not isinstance(self.verify, (str, bool)) or self.verify is False:
            raise MonitoringError("TLS_CONFIGURATION_INVALID")
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["Authorization"] = f"PVEAPIToken={token_id}={token_secret}"

    def get(self, path, **params):
        try:
            response = self.session.get(self.base + path, params=params, timeout=(3, 8),
                                        verify=self.verify, allow_redirects=False)
            if response.status_code in (401, 403):
                raise MonitoringError("ACCESS_DENIED")
            if response.status_code != 200:
                raise MonitoringError("API_UNAVAILABLE")
            if len(response.content) > MAX_SNAPSHOT_BYTES:
                raise MonitoringError("RESPONSE_TOO_LARGE")
            body = response.json()
            if not isinstance(body, dict) or "data" not in body:
                raise MonitoringError("INVALID_RESPONSE")
            return body["data"]
        except requests.exceptions.SSLError:
            raise MonitoringError("TLS_VERIFICATION_FAILED") from None
        except (requests.RequestException, ValueError, OSError):
            raise MonitoringError("CONNECTION_FAILED") from None

    def close(self):
        self.session.close()


def ids(value):
    if isinstance(value, list):
        return {str(x) for x in value}
    return set(re.findall(r"\d+", str(value or "")))


def selected(vmid, jobs, node):
    """None means unknown (pool-based jobs require a separate membership check)."""
    uncertain = False
    for job in jobs:
        if not isinstance(job, dict) or not job.get("enabled", 1):
            continue
        if job.get("node") and job["node"] != node:
            continue
        if job.get("pool"):
            uncertain = True
        elif job.get("all") and str(vmid) not in ids(job.get("exclude")):
            return True
        elif str(vmid) in ids(job.get("vmid")):
            return True
    return None if uncertain else False


def collect_host(config):
    host = {"name": config["name"], "observed_at": time.time(), "state": "unavailable",
            "cpu": None, "memory": {}, "root": {}, "storage": [], "vms": [], "tasks": [],
            "errors": []}
    reader = None
    try:
        reader = ProxmoxReader(config)
        prefix = "/nodes/" + quote(config["node"], safe="")
        status = reader.get(prefix + "/status")
        if not isinstance(status, dict):
            raise MonitoringError("INVALID_RESPONSE")
        cpu = number(status.get("cpu"))
        host.update(state="connected", cpu=None if cpu is None else round(min(1, cpu) * 100, 1),
                    memory=status.get("memory", {}), root=status.get("rootfs", {}),
                    uptime=number(status.get("uptime")))
        # A failed sub-check never makes a reachable host look entirely offline.
        def part(path, expected=list, **params):
            try:
                result = reader.get(path, **params)
                if not isinstance(result, expected):
                    raise MonitoringError("INVALID_RESPONSE")
                return result
            except MonitoringError as exc:
                host["errors"].append(str(exc))
                return None

        storage = part(prefix + "/storage")
        vms = part(prefix + "/qemu")
        jobs = part("/cluster/backup")
        tasks = part(prefix + "/tasks", typefilter="vzdump", limit=50)
        host["storage"] = storage or []
        host["tasks"] = tasks or []
        host["inventory_available"] = vms is not None
        archives = {}
        archives_complete = storage is not None
        stores = [item for item in storage or [] if isinstance(item, dict)
                  and "backup" in str(item.get("content", "")).split(",")]
        if not stores:
            archives_complete = False
        for item in stores:
            content = part(prefix + "/storage/" + quote(str(item.get("storage", "")), safe="")
                           + "/content", content="backup")
            if content is None:
                archives_complete = False
            for archive in content or []:
                if not isinstance(archive, dict):
                    continue
                vmid = archive.get("vmid")
                stamp = number(archive.get("ctime"))
                if vmid is not None and stamp:
                    archives[str(vmid)] = max(stamp, archives.get(str(vmid), 0))
        for vm in vms or []:
            if not isinstance(vm, dict) or number(vm.get("vmid")) is None:
                continue
            host["vms"].append({"vmid": vm["vmid"], "name": vm.get("name"),
                "status": vm.get("status"), "template": bool(vm.get("template")),
                "selected": selected(vm["vmid"], jobs, config["node"]) if jobs is not None else None,
                "backup_at": archives.get(str(vm["vmid"])), "archives_complete": archives_complete})
        host["state"] = "partial" if host["errors"] else "connected"
    except MonitoringError as exc:
        host["errors"].append(str(exc))
    finally:
        if reader:
            reader.close()
    return normalize_host(host)


def normalize_host(raw):
    """Drop all fields except approved metrics. Never persist raw API responses."""
    def usage(value):
        value = value if isinstance(value, dict) else {}
        return {key: number(value.get(key)) for key in ("used", "total")}

    host = {"name": label(raw.get("name"), 64), "observed_at": stamp(raw.get("observed_at")),
            "state": raw.get("state") if raw.get("state") in ("connected", "partial", "unavailable") else "unavailable",
            "cpu": number(raw.get("cpu")), "memory": usage(raw.get("memory")),
            "root": usage(raw.get("root")), "uptime": number(raw.get("uptime")),
            "errors": [x for x in raw.get("errors", []) if x in ERROR_CODES][:8],
            "inventory_available": raw.get("inventory_available") is True,
            "storage": [], "vms": [], "tasks": []}
    for disk in raw.get("storage", [])[:100]:
        if isinstance(disk, dict):
            host["storage"].append({"name": label(disk.get("storage", disk.get("name")), 64),
                "active": bool(disk.get("active")), "used": number(disk.get("used")),
                "total": number(disk.get("total")), "type": label(disk.get("type"), 20)})
    for vm in raw.get("vms", [])[:2000]:
        if not isinstance(vm, dict) or number(vm.get("vmid")) is None:
            continue
        host["vms"].append({"vmid": int(vm["vmid"]), "name": label(vm.get("name")),
            "status": vm.get("status") if vm.get("status") in ("running", "stopped") else "unknown",
            "template": bool(vm.get("template")), "selected": vm.get("selected") if type(vm.get("selected")) is bool else None,
            "backup_at": stamp(vm.get("backup_at")), "archives_complete": bool(vm.get("archives_complete"))})
    for task in raw.get("tasks", [])[:50]:
        if isinstance(task, dict):
            host["tasks"].append({"starttime": stamp(task.get("starttime")), "endtime": stamp(task.get("endtime")),
                "status": "OK" if task.get("status") == "OK" else ("FAILED" if task.get("endtime") else "RUNNING"),
                "id": label(task.get("id"), 30)})
    return host


def write_snapshot(hosts):
    path = Path(settings.MONITORING_SNAPSHOT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "collected_at": time.time(),
            "hosts": [normalize_host(host) for host in hosts]}
    payload = json.dumps(data, allow_nan=False)
    if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
        raise MonitoringError("Snapshot is too large.")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temp_name = handle.name
            os.chmod(temp_name, 0o600)
            handle.write(payload)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def read_snapshot():
    try:
        with open(settings.MONITORING_SNAPSHOT_PATH, "rb") as handle:
            payload = handle.read(MAX_SNAPSHOT_BYTES + 1)
        if len(payload) > MAX_SNAPSHOT_BYTES:
            return None
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("hosts"), list):
            return None
        return {"collected_at": stamp(data.get("collected_at")),
                "hosts": [normalize_host(x) for x in data["hosts"][:8] if isinstance(x, dict)]}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def dashboard(snapshot=None):
    snapshot = read_snapshot() if snapshot is None else snapshot
    now = time.time()
    if not snapshot:
        return {"hosts": [], "vms": [], "tasks": [], "issues": [], "connected": 0,
                "running": 0, "stopped": 0, "protected": 0, "backup_attention": 0,
                "observed_at": None, "stale": False, "empty": True}
    collected = stamp(snapshot.get("collected_at"))
    age = now - collected if collected else float("inf")
    stale = age > settings.MONITORING_STALE_SECONDS or age < -60
    hosts, vms, tasks, issues = [], [], [], []
    for raw in snapshot["hosts"]:
        host = normalize_host(raw)
        host_age = now - host["observed_at"] if host["observed_at"] else float("inf")
        host["stale"] = stale or host_age > settings.MONITORING_STALE_SECONDS or host_age < -60
        host["memory_percent"] = percent(host["memory"]["used"], host["memory"]["total"])
        host["memory_used"] = size(host["memory"]["used"])
        host["memory_total"] = size(host["memory"]["total"])
        host["cpu"] = min(100, host["cpu"]) if host["cpu"] is not None else None
        host["uptime_days"] = round(host["uptime"] / 86400, 1) if host["uptime"] is not None else None
        host["tone"] = "unknown" if host["stale"] else ("good" if host["state"] == "connected" else "warning")
        host["state_label"] = "Stale data" if host["stale"] else {
            "connected": "Reporting", "partial": "Partial data", "unavailable": "Unavailable"}[host["state"]]
        if host["state"] != "connected" or host["stale"]:
            issues.append({"host": host["name"], "title": host["state_label"],
                           "detail": "Check the collector connection and read-only access."})
        if host["root"]["total"] is not None:
            host["storage"].insert(0, {"name": "Host root filesystem", "type": "filesystem", "active": True,
                                       **host["root"]})
        for disk in host["storage"]:
            disk["percent"] = percent(disk["used"], disk["total"])
            disk["used_label"], disk["total_label"] = size(disk["used"]), size(disk["total"])
            disk["warning"] = not disk["active"] or (disk["percent"] is not None and disk["percent"] >= 80)
            if disk["warning"]:
                issues.append({"host": host["name"], "title": "Storage needs attention",
                               "detail": disk["name"] + (" is unavailable." if not disk["active"] else " is at least 80% full.")})
        for vm in host["vms"]:
            vm.update(host=host["name"], stale=host["stale"])
            backup_age = now - vm["backup_at"] if vm["backup_at"] else None
            if vm["selected"] is None or (not vm["archives_complete"] and not vm["backup_at"]):
                vm["backup_state"], vm["backup_label"] = "unknown", "Not verified"
            elif vm["selected"] is False:
                vm["backup_state"], vm["backup_label"] = "excluded", "Outside schedule"
            elif backup_age is None:
                # Proxmox can return HTTP 200 with an ACL-filtered empty list.
                # Absence from that list does not establish a missing backup.
                vm["backup_state"], vm["backup_label"] = "unknown", "Not verified"
            elif backup_age < -60 or backup_age > settings.MONITORING_BACKUP_MAX_AGE_HOURS * 3600:
                vm["backup_state"], vm["backup_label"] = "warning", "Archive overdue"
            else:
                vm["backup_state"], vm["backup_label"] = "good", "Recent archive"
            if vm["backup_state"] == "warning":
                issues.append({"host": host["name"], "title": "Backup archive needs attention",
                               "detail": f"VM {vm['vmid']}: {vm['backup_label'].lower()}."})
            vm["backup_date"] = date(vm["backup_at"])
            vms.append(vm)
        for task in host["tasks"]:
            task.update(host=host["name"], date=date(task["starttime"]))
            tasks.append(task)
        completed = sorted((t for t in host["tasks"] if t["endtime"]), key=lambda t: t["endtime"], reverse=True)
        if completed and completed[0]["status"] == "FAILED":
            issues.append({"host": host["name"], "title": "Most recent backup task failed",
                           "detail": "Review the backup task log in Proxmox."})
        hosts.append(host)
    vms.sort(key=lambda vm: (vm["host"], vm["vmid"]))
    tasks.sort(key=lambda task: task["starttime"] or 0, reverse=True)
    return {"hosts": hosts, "vms": vms, "tasks": tasks[:12], "issues": issues[:20],
            "connected": sum(h["state"] == "connected" and not h["stale"] for h in hosts),
            "inventory_complete": all(h["inventory_available"] for h in hosts),
            "running": sum(v["status"] == "running" for v in vms),
            "stopped": sum(v["status"] == "stopped" and not v["template"] for v in vms),
            "protected": sum(v["backup_state"] == "good" for v in vms),
            "backup_attention": sum(v["backup_state"] == "warning" for v in vms),
            "observed_at": date(collected),
            "stale": stale or any(h["stale"] for h in hosts), "empty": not hosts}
