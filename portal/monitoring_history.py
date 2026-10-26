"""Read-only Proxmox RRD history for the Graphs tab.

Only GET requests to Proxmox's own RRD endpoints are made, on the web server, using the same
read-only monitoring tokens as the collector. Nothing is written to a database or disk: results are
kept in Django's cache for a short time. Browsers never see Proxmox URLs, tokens or raw responses.

  /nodes/{node}/rrddata                     node CPU, memory, root filesystem and network (Sys.Audit)
  /nodes/{node}/storage/{storage}/rrddata   storage used/total

Missing samples stay missing (None -> a gap in the chart); they are never converted to zero.
"""
import hashlib
import time
from statistics import median
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache

from .monitoring import (ERROR_CODES, MonitoringError, ProxmoxReader, host_configs, label, number,
                         percent, thresholds)

# timeframe is the Proxmox RRD consolidation to request; the window then trims it to what was asked.
# "day" returns at least 24 hours and "week" at least 7 days in every supported Proxmox release.
RANGES = {
    "1h": {"seconds": 3600, "timeframe": "hour", "label": "1 hour", "default_step": 60},
    "24h": {"seconds": 86400, "timeframe": "day", "label": "24 hours", "default_step": 1800},
    "7d": {"seconds": 604800, "timeframe": "week", "label": "7 days", "default_step": 10800},
}
HISTORY_CODES = ERROR_CODES | {"TIMEOUT", "BUSY", "CONFIGURATION_INVALID", "NO_SNAPSHOT"}
MAX_STORAGES = 8
MAX_ROWS = 2000
DEFAULT_CACHE_SECONDS = {"1h": 60, "24h": 300, "7d": 900}
FAILURE_CACHE_SECONDS = 15
PARTIAL_CACHE_SECONDS = 30
LAST_GOOD_SECONDS = 6 * 3600
NETWORK_SCOPE = ("Host total: Proxmox's sum of the node's physical network interfaces. "
                 "Bridges and VM interfaces are not added; no per-interface breakdown is available here.")


def bits_per_second(bytes_per_second):
    """Proxmox netin/netout are bytes per second; charts use bits per second (x8)."""
    value = number(bytes_per_second)
    return None if value is None else round(value * 8, 1)


def cpu_percent(fraction):
    """Node RRD cpu is a 0..1 fraction of all cores (same meaning as /status)."""
    value = number(fraction)
    return None if value is None else round(min(1, value) * 100, 1)


def clean_rows(rows, start, end):
    """Rows inside [start, end], oldest first, one per timestamp. Junk rows are dropped."""
    unique = {}
    for row in rows[-MAX_ROWS:] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        moment = number(row.get("time"))
        if moment is None or moment < start or moment > end:
            continue
        unique[int(moment)] = row
    return [(moment, unique[moment]) for moment in sorted(unique)]


def sample_step(times, default):
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    return int(median(gaps)) if gaps else default


def time_grid(times, step):
    """Sorted unique timestamps. A filler is added after any hole wider than 1.5 steps so a chart
    breaks the line there instead of joining across the outage."""
    grid = []
    for moment in sorted(set(times)):
        if grid and moment - grid[-1] > step * 1.5:
            grid.append(grid[-1] + step)
        grid.append(moment)
    return grid


def column(rows, grid, getter):
    by_time = {moment: getter(row) for moment, row in rows}
    return [by_time.get(moment) for moment in grid]


def has_data(values):
    return any(value is not None for value in values)


def chart_state(values, error):
    if has_data(values):
        return "ok"
    return "error" if error else "empty"


def cache_key(host, range_key, suffix=""):
    digest = hashlib.sha256(host.encode()).hexdigest()[:20]
    return f"monitoring:history:{digest}:{range_key}{suffix}"


def error_code(exc):
    code = str(exc)
    return code if code in HISTORY_CODES else "API_UNAVAILABLE"


def storage_targets(snapshot_host):
    """Storage names come only from the saved snapshot, never from the request."""
    names = []
    for disk in (snapshot_host or {}).get("storage", []):
        if (disk.get("active") and disk.get("total") and disk.get("name") and not disk.get("root")
                and disk["name"] not in names):
            names.append(disk["name"])
    return names[:MAX_STORAGES]


def build_history(config, range_key, snapshot_host=None, now=None, budget=None):
    """Fetch and shape one host/range. Never raises: failures become per-chart error codes."""
    spec = RANGES[range_key]
    now = time.time() if now is None else now
    start, end = now - spec["seconds"], now + 120
    budget = settings.MONITORING_HISTORY_BUDGET_SECONDS if budget is None else budget
    began = time.monotonic()
    errors, node_error, node_rows, storage_rows, storage_errors = [], None, [], {}, {}
    names = storage_targets(snapshot_host)
    reader = None
    try:
        reader = ProxmoxReader(config)
        prefix = "/nodes/" + quote(config["node"], safe="")

        def fetch(path):
            if time.monotonic() - began > budget:
                raise MonitoringError("TIMEOUT")
            result = reader.get(path, timeframe=spec["timeframe"], cf="AVERAGE")
            if not isinstance(result, list):
                raise MonitoringError("INVALID_RESPONSE")
            return clean_rows(result, start, end)

        try:
            node_rows = fetch(prefix + "/rrddata")
        except MonitoringError as exc:
            node_error = error_code(exc)
        for name in names:
            try:
                storage_rows[name] = fetch(prefix + "/storage/" + quote(name, safe="") + "/rrddata")
            except MonitoringError as exc:
                storage_errors[name] = error_code(exc)
                if error_code(exc) in ("CREDENTIALS_MISSING", "TLS_VERIFICATION_FAILED", "CONNECTION_FAILED"):
                    # The host itself is unreachable; do not wait on every remaining storage.
                    for rest in names[names.index(name) + 1:]:
                        storage_errors[rest] = error_code(exc)
                    break
    except MonitoringError as exc:  # credentials/TLS configuration problems before any request
        node_error = error_code(exc)
        storage_errors = {name: node_error for name in names}
    finally:
        if reader:
            reader.close()

    all_times = [moment for moment, _ in node_rows]
    for rows in storage_rows.values():
        all_times += [moment for moment, _ in rows]
    step = sample_step(sorted(set(all_times)), spec["default_step"])
    grid = time_grid(all_times, step)

    memory_used = column(node_rows, grid, lambda row: number(row.get("memused")))
    memory_total = column(node_rows, grid, lambda row: number(row.get("memtotal")))
    cpu = column(node_rows, grid, lambda row: cpu_percent(row.get("cpu")))
    memory = [percent(u, t) for u, t in zip(memory_used, memory_total)]
    root = column(node_rows, grid, lambda row: percent(row.get("rootused"), row.get("roottotal")))
    receive = column(node_rows, grid, lambda row: bits_per_second(row.get("netin")))
    transmit = column(node_rows, grid, lambda row: bits_per_second(row.get("netout")))

    series = []
    if node_rows or node_error:
        series.append({"key": "root", "name": "Root filesystem", "error": node_error, "values": root})
    for name in names:
        series.append({"key": "storage:" + name, "name": label(name, 64), "error": storage_errors.get(name),
                       "values": column(storage_rows.get(name, []), grid,
                                        lambda row: percent(row.get("used"), row.get("total")))})
    storage_values = [item["values"] for item in series]
    storage_failed = [item["error"] for item in series if item.get("error")]
    charts = {
        "cpu": {"state": chart_state(cpu, node_error), "error": node_error, "values": cpu},
        "memory": {"state": chart_state(memory, node_error), "error": node_error, "values": memory,
                   "used": memory_used, "total": memory_total},
        "storage": {"state": "ok" if any(has_data(v) for v in storage_values) else
                    ("error" if (node_error or storage_failed) else "empty"),
                    "error": node_error or (storage_failed[0] if storage_failed else None), "series": series,
                    "note": None if names else "Storage names come from the latest saved collection."},
        "network": {"state": chart_state(receive + transmit, node_error), "error": node_error,
                    "unit": "bit/s", "scope": "host", "scope_label": NETWORK_SCOPE,
                    "receive": receive, "transmit": transmit},
    }
    for chart in charts.values():
        if chart["error"]:
            errors.append(chart["error"])
    for item in series:
        if item.get("error"):
            errors.append(item["error"])
    states = [chart["state"] for chart in charts.values()]
    last_values = [grid[i] for i, _ in enumerate(grid)
                   if any(v[i] is not None for v in (cpu, memory, receive, transmit, *storage_values))]
    return {
        "host": config["name"], "range": range_key, "range_label": spec["label"], "timeframe": spec["timeframe"],
        "window_start": int(start), "window_end": int(now), "step_seconds": step, "times": grid,
        "charts": charts, "errors": sorted(set(errors)), "fetched_at": int(now),
        "last_sample_at": max(last_values) if last_values else None,
        "status": history_status(states, errors), "stale": False, "cache": "miss",
    }


def history_status(states, errors):
    if all(state in ("error", "empty") for state in states):
        return "unavailable" if errors else "empty"
    return "partial" if "error" in states else "ok"


def usable(payload):
    return payload["status"] in ("ok", "partial") and any(c["state"] == "ok" for c in payload["charts"].values())


def ttl_for(range_key):
    configured = getattr(settings, "MONITORING_HISTORY_CACHE_SECONDS", {})
    value = number(configured.get(range_key) if isinstance(configured, dict) else None)
    return int(value) if value else DEFAULT_CACHE_SECONDS[range_key]


def unavailable(host, range_key, code):
    return {"host": host, "range": range_key, "range_label": RANGES[range_key]["label"], "times": [],
            "charts": {}, "errors": [code], "status": "unavailable", "stale": False, "cache": "miss",
            "fetched_at": int(time.time()), "last_sample_at": None, "step_seconds": None,
            "window_start": None, "window_end": None}


def get_history(host, range_key, snapshot_host=None):
    """Cached history for a configured host. Raises LookupError for unknown hosts or ranges.

    Repeated tab switches and browser polls are served from cache; at most one request per host and
    range talks to Proxmox at a time, and a failing Proxmox is retried only every few seconds."""
    if range_key not in RANGES:
        raise LookupError("range")
    try:
        configs = host_configs()
    except MonitoringError:
        return unavailable(host, range_key, "CONFIGURATION_INVALID")
    config = next((item for item in configs if item["name"] == host), None)
    if config is None:
        raise LookupError("host")
    key, last_key, lock_key = cache_key(host, range_key), cache_key(host, range_key, ":last"), cache_key(host, range_key, ":lock")
    hit = cache.get(key)
    if hit and hit.get("cache") == "failure":
        # A recent load failed: do not hit Proxmox again yet, show the last good charts if any.
        return fall_back(host, range_key, last_key, None, hit)
    if hit:
        return {**hit, "cache": "hit"}
    if not cache.add(lock_key, 1, timeout=int(settings.MONITORING_HISTORY_BUDGET_SECONDS) + 5):
        # Another request is already loading this history; wait briefly for its result.
        deadline = time.monotonic() + settings.MONITORING_HISTORY_BUDGET_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.25)
            hit = cache.get(key)
            if hit:
                return {**hit, "cache": "hit"}
            if not cache.get(lock_key):
                break
        hit = cache.get(key)
        if hit and hit.get("cache") != "failure":
            return {**hit, "cache": "hit"}
        return fall_back(host, range_key, last_key, "BUSY", hit)
    try:
        payload = build_history(config, range_key, snapshot_host)
        if usable(payload):
            ttl = ttl_for(range_key) if payload["status"] == "ok" else PARTIAL_CACHE_SECONDS
            cache.set(key, payload, ttl)
            cache.set(last_key, payload, LAST_GOOD_SECONDS)
            return payload
        cache.set(key, {**payload, "cache": "failure"}, FAILURE_CACHE_SECONDS)
        return fall_back(host, range_key, last_key, None, payload)
    finally:
        cache.delete(lock_key)


def fall_back(host, range_key, last_key, code, payload=None):
    """Serve the last good history, clearly marked stale, when a fresh load failed."""
    last = cache.get(last_key)
    if last:
        errors = sorted(set(last.get("errors", []) + ((payload or {}).get("errors") or ([code] if code else []))))
        return {**last, "stale": True, "errors": errors, "cache": "last-good"}
    return payload or unavailable(host, range_key, code or "API_UNAVAILABLE")


def current_values(dashboard_host):
    """The saved snapshot's latest values, kept separate from the last historical sample."""
    if not dashboard_host:
        return None
    return {"cpu": dashboard_host.get("cpu"), "memory": dashboard_host.get("memory_percent"),
            "storage": {disk["name"]: disk.get("percent") for disk in dashboard_host.get("storage", [])},
            "stale": bool(dashboard_host.get("stale")), "thresholds": thresholds()}
