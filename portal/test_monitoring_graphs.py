"""Fixture-based tests for the Monitoring Overview/Graphs tabs. No test contacts Proxmox."""
import json
import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import monitoring_history as history
from .monitoring import MonitoringError, dashboard, thresholds
from .test_management import force_staff_login
from .test_monitoring import snapshot

HOSTS = json.dumps([
    {"name": "vps01", "node": "vps01", "url": "https://vps01.example:8006",
     "token_id_env": "T_ID", "token_secret_env": "T_SECRET"},
    {"name": "test-1", "node": "test-1", "url": "https://test-1.example:8006",
     "token_id_env": "T_ID", "token_secret_env": "T_SECRET"}])
GIB = 1024 ** 3


class FakeReader:
    """Stands in for ProxmoxReader. Records every request so tests can assert GET-only, bounded use."""
    calls = []
    node_rows = []
    storage_rows = {}
    fail = {}          # path fragment -> error code

    def __init__(self, config):
        self.config = config

    def get(self, path, **params):
        FakeReader.calls.append((path, params))
        for fragment, code in FakeReader.fail.items():
            if fragment in path:
                raise MonitoringError(code)
        if "/storage/" in path:
            return FakeReader.storage_rows.get(path.split("/storage/")[1].split("/")[0], [])
        return FakeReader.node_rows

    def close(self):
        pass


def reset_fake(node_rows=None, storage_rows=None, fail=None):
    FakeReader.calls, FakeReader.fail = [], dict(fail or {})
    FakeReader.node_rows, FakeReader.storage_rows = node_rows or [], storage_rows or {}


def node_row(moment, cpu=0.05, used=8 * GIB, total=16 * GIB, netin=125000, netout=250000):
    return {"time": moment, "cpu": cpu, "memused": used, "memtotal": total,
            "rootused": 20 * GIB, "roottotal": 100 * GIB, "netin": netin, "netout": netout}


def snapshot_host(name="vps01"):
    return {"name": name, "storage": [
        {"name": "local-lvm", "active": True, "total": 800 * GIB, "used": 30 * GIB},
        {"name": "Root filesystem", "active": True, "total": 100 * GIB, "used": 20 * GIB, "root": True},
        {"name": "dead", "active": False, "total": 1, "used": 1}]}


class HistoryMathTests(SimpleTestCase):
    def test_network_bytes_per_second_become_bits_per_second(self):
        self.assertEqual(history.bits_per_second(125000), 1_000_000)   # 1 Mbit/s
        self.assertIsNone(history.bits_per_second(None))
        self.assertIsNone(history.bits_per_second(-5))
        self.assertIsNone(history.bits_per_second("fast"))

    def test_cpu_fraction_becomes_percent_and_unknown_stays_unknown(self):
        self.assertEqual(history.cpu_percent(0.014), 1.4)
        self.assertEqual(history.cpu_percent(7), 100)       # clamped, never above 100%
        self.assertIsNone(history.cpu_percent(None))        # never converted to 0

    def test_rows_outside_window_junk_and_duplicates_are_dropped(self):
        rows = [{"time": 5}, {"time": 100}, {"time": 100, "cpu": 1}, "junk", {"time": None}, {"time": 500}, {"time": 10 ** 6}]
        kept = history.clean_rows(rows, 50, 600)
        self.assertEqual([moment for moment, _ in kept], [100, 500])
        self.assertEqual(kept[0][1], {"time": 100, "cpu": 1})  # latest duplicate wins
        self.assertEqual(history.clean_rows("not a list", 0, 10), [])

    def test_hole_in_samples_gets_a_filler_so_charts_break_the_line(self):
        grid = history.time_grid([0, 60, 120, 1000, 1060], 60)
        self.assertEqual(grid, [0, 60, 120, 180, 1000, 1060])
        self.assertEqual(history.time_grid([0, 60, 120], 60), [0, 60, 120])

    def test_ranges_are_supported_and_bounded(self):
        self.assertEqual(set(history.RANGES), {"1h", "24h", "7d"})
        self.assertEqual(history.RANGES["1h"]["timeframe"], "hour")
        self.assertEqual(history.RANGES["24h"]["timeframe"], "day")
        self.assertEqual(history.RANGES["7d"]["timeframe"], "week")


@override_settings(MONITORING_HOSTS_JSON=HOSTS, MONITORING_HISTORY_BUDGET_SECONDS=10)
class BuildHistoryTests(SimpleTestCase):
    config = {"name": "vps01", "node": "vps01"}

    def run_build(self, range_key="24h", now=100000, **kw):
        with patch.object(history, "ProxmoxReader", FakeReader):
            return history.build_history(self.config, range_key, snapshot_host(), now=now, **kw)

    def test_units_and_values(self):
        now = 100000
        reset_fake([node_row(now - 120), node_row(now - 60, cpu=0.5, used=12 * GIB)],
                   {"local-lvm": [{"time": now - 60, "used": 40 * GIB, "total": 800 * GIB}]})
        payload = self.run_build(now=now)
        charts = payload["charts"]
        self.assertEqual(charts["cpu"]["values"], [5.0, 50.0])
        self.assertEqual(charts["memory"]["values"], [50.0, 75.0])
        self.assertEqual(charts["network"]["receive"], [1_000_000, 1_000_000])
        self.assertEqual(charts["network"]["transmit"], [2_000_000, 2_000_000])
        self.assertEqual(charts["network"]["unit"], "bit/s")
        self.assertEqual(charts["network"]["scope"], "host")
        self.assertIn("physical", charts["network"]["scope_label"])
        names = [item["name"] for item in charts["storage"]["series"]]
        self.assertEqual(names, ["Root filesystem", "local-lvm"])   # inactive storage is not requested
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["last_sample_at"], now - 60)

    def test_only_get_rrd_endpoints_with_a_bounded_set_of_requests(self):
        reset_fake([node_row(99000)], {"local-lvm": [{"time": 99000, "used": 1, "total": 2}]})
        self.run_build("7d")
        paths = [path for path, _ in FakeReader.calls]
        self.assertEqual(paths, ["/nodes/vps01/rrddata", "/nodes/vps01/storage/local-lvm/rrddata"])
        for _, params in FakeReader.calls:
            self.assertEqual(params, {"timeframe": "week", "cf": "AVERAGE"})

    def test_missing_samples_stay_gaps_never_zero(self):
        now = 100000
        rows = [node_row(now - 7200), {"time": now - 7140}, node_row(now - 7080, netin=None)]
        reset_fake(rows)
        charts = self.run_build(now=now)["charts"]
        self.assertEqual(charts["cpu"]["values"], [5.0, None, 5.0])
        self.assertEqual(charts["memory"]["values"], [50.0, None, 50.0])
        self.assertEqual(charts["network"]["receive"], [1_000_000, None, None])
        self.assertNotIn(0, [v for v in charts["cpu"]["values"] if v is None])

    def test_idle_zero_is_kept_as_real_zero(self):
        now = 100000
        reset_fake([node_row(now - 60, cpu=0, netin=0, netout=0)])
        charts = self.run_build(now=now)["charts"]
        self.assertEqual(charts["cpu"]["values"], [0.0])
        self.assertEqual(charts["network"]["receive"], [0.0])

    def test_storage_denied_is_partial_and_other_charts_remain(self):
        now = 100000
        reset_fake([node_row(now - 60)], fail={"/storage/": "ACCESS_DENIED"})
        payload = self.run_build(now=now)
        self.assertEqual(payload["status"], "ok" if payload["charts"]["storage"]["state"] == "ok" else "partial")
        self.assertEqual(payload["charts"]["cpu"]["state"], "ok")
        self.assertEqual(payload["charts"]["storage"]["state"], "ok")  # root filesystem comes from node RRD
        errored = [item for item in payload["charts"]["storage"]["series"] if item["error"]]
        self.assertEqual([item["error"] for item in errored], ["ACCESS_DENIED"])
        self.assertIn("ACCESS_DENIED", payload["errors"])

    def test_node_failure_reports_error_without_raising(self):
        reset_fake(fail={"/rrddata": "CONNECTION_FAILED"})
        payload = self.run_build()
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["charts"]["cpu"]["state"], "error")
        self.assertEqual(payload["charts"]["cpu"]["error"], "CONNECTION_FAILED")

    def test_unreachable_host_does_not_wait_on_every_storage(self):
        reset_fake(fail={"/storage/": "CONNECTION_FAILED"}, node_rows=[node_row(99000)])
        self.run_build(now=100000)
        storage_calls = [path for path, _ in FakeReader.calls if "/storage/" in path]
        self.assertEqual(len(storage_calls), 1)

    def test_missing_credentials_become_a_code_not_an_exception(self):
        class NoCredentials:
            def __init__(self, config):
                raise MonitoringError("CREDENTIALS_MISSING")
        with patch.object(history, "ProxmoxReader", NoCredentials):
            payload = history.build_history(self.config, "1h", snapshot_host(), now=100000)
        self.assertEqual(payload["status"], "unavailable")
        self.assertIn("CREDENTIALS_MISSING", payload["errors"])

    def test_time_budget_stops_further_requests(self):
        reset_fake([node_row(99000)], {"local-lvm": [{"time": 99000, "used": 1, "total": 2}]})
        payload = self.run_build(now=100000, budget=-1)
        self.assertEqual(FakeReader.calls, [])
        self.assertIn("TIMEOUT", payload["errors"])

    def test_empty_history_is_empty_not_error(self):
        reset_fake([])
        payload = self.run_build()
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["charts"]["cpu"]["state"], "empty")


@override_settings(MONITORING_HOSTS_JSON=HOSTS, MONITORING_HISTORY_BUDGET_SECONDS=2)
class CachingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.patch = patch.object(history, "ProxmoxReader", FakeReader)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(cache.clear)

    def test_repeated_requests_use_the_cache(self):
        now = time.time()
        reset_fake([node_row(now - 60)])
        first = history.get_history("vps01", "1h", snapshot_host())
        calls = len(FakeReader.calls)
        second = history.get_history("vps01", "1h", snapshot_host())
        self.assertGreater(calls, 0)
        self.assertEqual(len(FakeReader.calls), calls)
        self.assertEqual(second["cache"], "hit")
        self.assertEqual(first["charts"]["cpu"]["values"], second["charts"]["cpu"]["values"])

    def test_ranges_and_hosts_are_cached_separately(self):
        reset_fake([node_row(time.time() - 60)])
        history.get_history("vps01", "1h")
        history.get_history("vps01", "24h")
        history.get_history("test-1", "1h")
        self.assertEqual(len([c for c in FakeReader.calls if c[0].endswith("/rrddata")]), 3)

    def test_failure_is_not_retried_immediately_and_last_good_is_served_stale(self):
        now = time.time()
        reset_fake([node_row(now - 60)])
        history.get_history("vps01", "1h")
        cache.delete(history.cache_key("vps01", "1h"))          # simulate expiry; last-good copy remains
        reset_fake(fail={"/rrddata": "CONNECTION_FAILED"})
        stale = history.get_history("vps01", "1h")
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["cache"], "last-good")
        self.assertIn("CONNECTION_FAILED", stale["errors"])
        self.assertTrue(stale["charts"]["cpu"]["values"])
        before = len(FakeReader.calls)
        history.get_history("vps01", "1h")                       # inside the failure back-off window
        self.assertEqual(len(FakeReader.calls), before)

    def test_failure_without_prior_history_is_unavailable(self):
        reset_fake(fail={"/rrddata": "ACCESS_DENIED"})
        payload = history.get_history("vps01", "24h")
        self.assertEqual(payload["status"], "unavailable")
        self.assertFalse(payload["stale"])

    def test_unknown_host_and_range_are_rejected_before_any_request(self):
        reset_fake([node_row(time.time())])
        with self.assertRaises(LookupError):
            history.get_history("evil", "1h")
        with self.assertRaises(LookupError):
            history.get_history("vps01", "30d")
        self.assertEqual(FakeReader.calls, [])

    @override_settings(MONITORING_HOSTS_JSON="not json")
    def test_invalid_configuration_is_reported(self):
        payload = history.get_history("vps01", "1h")
        self.assertEqual(payload["errors"], ["CONFIGURATION_INVALID"])


@override_settings(MONITORING_HOSTS_JSON=HOSTS)
class GraphEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        reset_fake([node_row(time.time() - 60)])
        patcher = patch.object(history, "ProxmoxReader", FakeReader)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse("management:monitoring_history")
        self.owner = User.objects.create_user("owner", is_staff=True, is_superuser=True)

    def login_owner(self):
        force_staff_login(self.client, self.owner)

    def test_only_the_owner_may_read_history_or_overview(self):
        overview = reverse("management:monitoring_overview")
        for url in (self.url + "?host=vps01&range=1h", overview):
            self.assertEqual(self.client.get(url).status_code, 302)           # anonymous
            customer = User.objects.create_user("c" + str(len(url)))
            self.client.force_login(customer)
            self.assertEqual(self.client.get(url).status_code, 302)           # customer session
            self.client.logout()
        staff = User.objects.create_user("billing", is_staff=True)
        force_staff_login(self.client, staff)
        self.assertEqual(self.client.get(self.url + "?host=vps01&range=1h").status_code, 403)
        self.assertEqual(self.client.get(overview).status_code, 403)
        self.assertEqual(FakeReader.calls, [])                                # nothing reached Proxmox

    def test_customer_cookie_cannot_authorize_history(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url + "?host=vps01").status_code, 302)

    def test_owner_gets_json_that_is_never_cached_by_browsers(self):
        self.login_owner()
        with patch("portal.monitoring.read_snapshot", return_value=snapshot()):
            response = self.client.get(self.url, {"host": "vps01", "range": "1h"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        data = response.json()
        self.assertEqual(data["host"], "vps01")
        self.assertEqual(data["timezone"], "Asia/Manila")
        self.assertEqual(data["timezone_label"], "PHT")
        self.assertIn("charts", data)
        self.assertIn("thresholds", data)

    def test_response_contains_no_credentials_or_proxmox_addresses(self):
        self.login_owner()
        with patch.dict("os.environ", {"T_ID": "user@pve!tok", "T_SECRET": "SECRET-VALUE"}):
            body = self.client.get(self.url, {"host": "vps01", "range": "24h"}).content.decode()
        for forbidden in ("SECRET-VALUE", "user@pve", "vps01.example", ":8006", "PVEAPIToken"):
            self.assertNotIn(forbidden, body)

    def test_bad_range_and_unknown_host_are_client_errors(self):
        self.login_owner()
        self.assertEqual(self.client.get(self.url, {"host": "vps01", "range": "30d"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"host": "nope", "range": "1h"}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"host": "../../etc", "range": "1h"}).status_code, 404)
        self.assertEqual(FakeReader.calls, [])

    def test_post_is_not_allowed(self):
        self.login_owner()
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_history_survives_a_failing_proxmox_with_a_json_error_state(self):
        self.login_owner()
        reset_fake(fail={"/rrddata": "TLS_VERIFICATION_FAILED"})
        data = self.client.get(self.url, {"host": "test-1", "range": "1h"}).json()
        self.assertEqual(data["status"], "unavailable")
        self.assertIn("TLS_VERIFICATION_FAILED", data["errors"])


@override_settings(MONITORING_HOSTS_JSON=HOSTS)
class PageTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner", is_staff=True, is_superuser=True)
        force_staff_login(self.client, owner)

    @patch("requests.Session")
    @patch("portal.monitoring.read_snapshot", return_value=snapshot())
    def test_both_tabs_are_in_the_same_page_and_nothing_collects(self, read, session):
        response = self.client.get(reverse("management:monitoring"))
        self.assertContains(response, 'role="tablist"')
        self.assertContains(response, 'id="mon-panel-overview"')
        self.assertContains(response, 'id="mon-panel-graphs"')
        self.assertContains(response, 'data-history-url="' + reverse("management:monitoring_history") + '"')
        self.assertContains(response, 'value="vps01"')
        self.assertContains(response, 'value="test-1"')
        for key in ("1h", "24h", "7d"):
            self.assertContains(response, 'data-range="%s"' % key)
        self.assertContains(response, "vendor/uplot/uPlot.iife.min.js")
        self.assertContains(response, "does not start a new collection")
        session.assert_not_called()

    @patch("portal.monitoring.read_snapshot", return_value=snapshot())
    def test_overview_fragment_is_regions_only_and_reads_the_snapshot(self, read):
        response = self.client.get(reverse("management:monitoring_overview"))
        self.assertEqual(response.status_code, 200)
        for region in ("status", "alerts", "hosts", "storage", "vms", "backup"):
            self.assertContains(response, 'data-region="%s"' % region)
        self.assertNotContains(response, "<html")

    @override_settings(MONITORING_HOSTS_JSON="")
    @patch("portal.monitoring.read_snapshot", return_value=None)
    def test_graphs_empty_state_without_hosts(self, read):
        self.assertContains(self.client.get(reverse("management:monitoring")), "No monitoring hosts are configured.")

    @patch("portal.monitoring.read_snapshot")
    def test_overview_marks_reporting_separately_from_resource_health(self, read):
        data = snapshot()
        data["hosts"][0]["memory"] = {"used": 85, "total": 100}
        read.return_value = data
        html = self.client.get(reverse("management:monitoring")).content.decode()
        self.assertIn("Reporting", html)
        self.assertIn("Memory warning", html)
        self.assertIn("is at or above 80%", html)


class ResourceHealthTests(SimpleTestCase):
    def host_snapshot(self, cpu, used, total=100, age=0):
        data = snapshot(age)
        data["hosts"][0].update(cpu=cpu, memory={"used": used, "total": total})
        return dashboard(data)

    def test_levels_and_text_labels(self):
        host = self.host_snapshot(10, 50)["hosts"][0]
        self.assertEqual((host["cpu_level"], host["memory_level"], host["health_tone"]), ("ok", "ok", "good"))
        host = self.host_snapshot(10, 85)["hosts"][0]
        self.assertEqual(host["memory_level"], "warning")
        self.assertIn("Memory", host["health_label"])
        self.assertEqual(host["memory_note"], "Warning · at or above 80%")
        host = self.host_snapshot(97, 95)["hosts"][0]
        self.assertEqual((host["cpu_level"], host["memory_level"], host["health_tone"]), ("critical", "critical", "critical"))

    def test_collection_status_and_resource_health_are_independent(self):
        host = self.host_snapshot(10, 95)["hosts"][0]
        self.assertEqual(host["state"], "connected")      # reporting
        self.assertEqual(host["health_tone"], "critical")  # but unhealthy

    def test_unknown_readings_are_never_called_healthy(self):
        host = self.host_snapshot(None, 0, total=0)["hosts"][0]
        self.assertIsNone(host["cpu_level"])
        self.assertEqual(host["health_tone"], "unknown")

    def test_stale_hosts_neither_raise_alerts_nor_claim_health(self):
        result = self.host_snapshot(99, 99, age=600)
        self.assertEqual(result["alerts"], [])
        self.assertEqual(result["hosts"][0]["health_tone"], "unknown")
        self.assertEqual(result["freshness"], "stale")

    def test_alert_wording_matches_the_mockup(self):
        texts = [alert["text"] for alert in self.host_snapshot(10, 85)["alerts"]]
        self.assertIn("test-1 memory usage is at or above 80% — review capacity.", texts)

    @override_settings(MONITORING_THRESHOLDS={"memory": {"warning": 70, "critical": 95}})
    def test_configured_thresholds_are_used(self):
        self.assertEqual(self.host_snapshot(10, 75)["hosts"][0]["memory_level"], "warning")
        self.assertEqual(thresholds()["cpu"], {"warning": 85, "critical": 95})   # unspecified: documented default

    @override_settings(MONITORING_THRESHOLDS={"memory": {"warning": 99, "critical": 50}, "cpu": "oops"})
    def test_invalid_thresholds_fall_back_so_alerts_cannot_be_disabled(self):
        limits = thresholds()
        self.assertEqual(limits["memory"], {"warning": 80, "critical": 90})
        self.assertEqual(limits["cpu"], {"warning": 85, "critical": 95})

    def test_shared_storage_is_flagged_only_on_identical_byte_counts_and_never_summed(self):
        data = snapshot()
        data["hosts"][0]["root"] = {"used": 18, "total": 90}
        data["hosts"][0]["storage"] = [
            {"storage": "local", "type": "dir", "active": True, "used": 18, "total": 90},
            {"storage": "nas", "type": "nfs", "active": True, "used": 5, "total": 70},
            {"storage": "other", "type": "dir", "active": True, "used": 18, "total": 91}]
        disks = {d["name"]: d for d in dashboard(data)["hosts"][0]["storage"]}
        self.assertEqual(disks["local"]["same_capacity_as"], ["Root filesystem"])
        self.assertEqual(disks["Root filesystem"]["same_capacity_as"], ["local"])
        self.assertEqual(disks["nas"]["same_capacity_as"], [])
        self.assertEqual(disks["other"]["same_capacity_as"], [])
        self.assertEqual(disks["nas"]["type_label"], "NFS")

    def test_vms_and_templates_are_counted_separately(self):
        data = snapshot()
        data["hosts"][0]["vms"] += [
            {"vmid": 9000, "name": "tmpl", "status": "stopped", "template": True, "selected": True},
            {"vmid": 101, "name": "off", "status": "stopped", "selected": True}]
        host = dashboard(data)["hosts"][0]
        self.assertEqual((host["vm_count"], host["template_count"]), (2, 1))
        states = {vm["vmid"]: vm["state_key"] for vm in host["vms"]}
        self.assertEqual(states, {100: "running", 9000: "template", 101: "stopped"})

    def test_backup_visibility_limit_is_preserved(self):
        data = snapshot()
        data["hosts"][0]["vms"][0].update(backup_at=None, archives_complete=False)
        vm = dashboard(data)["vms"][0]
        self.assertEqual(vm["backup_label"], "Not verified")
