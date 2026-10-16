import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from .monitoring import (MonitoringError, ProxmoxReader, collect_host, dashboard,
                         host_configs, read_snapshot, selected, write_snapshot)
from .test_management import force_staff_login


CONFIG = {"name": "test-1", "node": "test-1", "url": "https://monitor.example:8006",
          "token_id_env": "TEST_PVE_ID", "token_secret_env": "TEST_PVE_SECRET"}


def snapshot(age=0):
    now = time.time() - age
    return {"version": 1, "collected_at": now, "hosts": [{"name": "test-1", "state": "connected",
        "observed_at": now, "inventory_available": True, "cpu": 20, "memory": {"used": 4, "total": 10},
        "root": {"used": 90, "total": 100}, "storage": [], "errors": [],
        "vms": [{"vmid": 100, "name": "WebServer", "status": "running", "selected": True,
                 "archives_complete": True, "backup_at": now - 3600}], "tasks": []}]}


class MonitoringAccessTests(TestCase):
    def test_anonymous_customer_and_staff_cannot_read_infrastructure(self):
        url = reverse("management:monitoring")
        self.assertEqual(self.client.get(url).status_code, 302)
        customer = User.objects.create_user("customer")
        self.client.force_login(customer)
        self.assertEqual(self.client.get(url).status_code, 302)
        staff = User.objects.create_user("staff", is_staff=True)
        force_staff_login(self.client, staff)
        self.assertEqual(self.client.get(url).status_code, 403)

    @patch("portal.monitoring.read_snapshot", return_value=None)
    @patch("requests.Session")
    def test_owner_empty_state_is_honest_and_page_never_collects(self, session, read):
        owner = User.objects.create_user("owner", is_staff=True, is_superuser=True)
        force_staff_login(self.client, owner)
        response = self.client.get(reverse("management:monitoring"))
        self.assertContains(response, "No live readings have been collected")
        self.assertContains(response, "Notifications off")
        self.assertContains(response, "management.css")
        self.assertContains(response, 'aria-current="page">Monitoring</a>')
        session.assert_not_called()
        self.assertContains(self.client.get(reverse("management:index")), "Infrastructure monitoring")
        self.assertEqual(self.client.post(reverse("management:monitoring")).status_code, 405)

    def test_monitoring_link_is_hidden_from_ordinary_staff(self):
        staff = User.objects.create_user("billing-operator", is_staff=True)
        force_staff_login(self.client, staff)
        self.assertNotContains(self.client.get(reverse("management:index")),
                               'href="' + reverse("management:monitoring") + '"')

    def test_customer_cookie_cannot_authorize_owner_monitoring(self):
        owner = User.objects.create_user("owner", is_staff=True, is_superuser=True)
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse("management:monitoring")).status_code, 302)

    @patch("portal.monitoring.read_snapshot")
    def test_saved_snapshot_renders_without_raw_secrets(self, read):
        read.return_value = snapshot()
        read.return_value["hosts"][0]["name"] = '<script>alert("host")</script>'
        read.return_value["hosts"][0]["authorization"] = "PRIVATE-TOKEN"
        owner = User.objects.create_user("owner", is_staff=True, is_superuser=True)
        force_staff_login(self.client, owner)
        response = self.client.get(reverse("management:monitoring"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent archive")
        self.assertNotContains(response, "PRIVATE-TOKEN")
        self.assertNotContains(response, '<script>alert("host")</script>')
        self.assertContains(response, "&lt;script&gt;")


class SnapshotTests(SimpleTestCase):
    def test_stale_readings_do_not_count_as_reporting(self):
        result = dashboard(snapshot(600))
        self.assertTrue(result["stale"])
        self.assertEqual(result["connected"], 0)
        self.assertEqual(result["hosts"][0]["tone"], "unknown")

    def test_absent_archive_is_unknown_and_disk_pressure_is_visible(self):
        data = snapshot()
        data["hosts"][0]["vms"][0]["backup_at"] = None
        result = dashboard(data)
        self.assertEqual(result["backup_attention"], 0)
        self.assertEqual(result["vms"][0]["backup_label"], "Not verified")
        self.assertTrue(any(i["title"] == "Storage needs attention" for i in result["issues"]))

    def test_denied_archive_check_is_unknown_not_missing_or_healthy(self):
        data = snapshot()
        data["hosts"][0]["vms"][0].update(backup_at=None, archives_complete=False)
        result = dashboard(data)
        self.assertEqual(result["vms"][0]["backup_label"], "Not verified")
        self.assertEqual(result["protected"], 0)

    def test_explicit_exclusions_and_pool_uncertainty(self):
        jobs = [{"all": 1, "exclude": "9000,9001,9002", "node": "vps01"}]
        self.assertTrue(selected(1026, jobs, "vps01"))
        self.assertFalse(selected(9000, jobs, "vps01"))
        self.assertFalse(selected(100, jobs, "test-1"))
        self.assertIsNone(selected(100, [{"pool": "customer"}], "test-1"))
        self.assertFalse(selected(100, [{"vmid": "100", "enabled": 0}], "test-1"))

    def test_future_invalid_and_overdue_archive_timestamps(self):
        for timestamp in (time.time() + 500, time.time() - 40 * 3600):
            data = snapshot()
            data["hosts"][0]["vms"][0]["backup_at"] = timestamp
            self.assertEqual(dashboard(data)["backup_attention"], 1)
        data = snapshot()
        data["hosts"][0]["vms"][0]["backup_at"] = 1e300
        self.assertEqual(dashboard(data)["vms"][0]["backup_label"], "Not verified")

    def test_failure_after_success_is_not_hidden(self):
        data = snapshot()
        now = time.time()
        data["hosts"][0]["tasks"] = [{"starttime": now - 20, "endtime": now - 10, "status": "OK"},
                                      {"starttime": now - 5, "endtime": now - 1, "status": "ERROR"}]
        self.assertTrue(any(i["title"] == "Most recent backup task failed" for i in dashboard(data)["issues"]))

    def test_missing_corrupt_or_oversized_snapshot_is_not_live_data(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "snapshot.json"
            with override_settings(MONITORING_SNAPSHOT_PATH=str(target)):
                self.assertIsNone(read_snapshot())
                target.write_text("broken")
                self.assertIsNone(read_snapshot())
                target.write_text(" " * 2_000_001)
                self.assertIsNone(read_snapshot())

    def test_atomic_snapshot_round_trip_omits_unapproved_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            with override_settings(MONITORING_SNAPSHOT_PATH=str(Path(temp) / "snapshot.json")):
                data = snapshot()["hosts"]
                data[0]["authorization"] = "PRIVATE-TOKEN"
                write_snapshot(data)
                result = read_snapshot()
                self.assertEqual(result["hosts"][0]["name"], "test-1")
                self.assertNotIn("PRIVATE-TOKEN", (Path(temp) / "snapshot.json").read_text())


class CollectorTests(SimpleTestCase):
    def test_plain_http_and_credential_url_rejected_before_connection(self):
        for url in ("http://host:8006", "https://user:password@host", "https://host/path"):
            with override_settings(MONITORING_HOSTS_JSON=json.dumps([{**CONFIG, "url": url}])):
                with self.assertRaises(MonitoringError):
                    host_configs()

    @patch.dict(os.environ, {"TEST_PVE_ID": "reader@pve!monitor", "TEST_PVE_SECRET": "PRIVATE-TOKEN"})
    @patch("portal.monitoring.requests.Session")
    def test_only_get_requests_and_tls_verification(self, session):
        client = session.return_value
        response = MagicMock(status_code=200, content=b'{}')
        response.json.return_value = {"data": {"cpu": 0.1}}
        client.get.return_value = response
        reader = ProxmoxReader(CONFIG)
        self.assertEqual(reader.get("/nodes/test-1/status"), {"cpu": 0.1})
        self.assertTrue(client.get.call_args.kwargs["verify"])
        self.assertFalse(client.get.call_args.kwargs["allow_redirects"])
        self.assertFalse(client.trust_env)
        client.post.assert_not_called()
        client.put.assert_not_called()
        client.delete.assert_not_called()
        reader.close()

    @patch.dict(os.environ, {"TEST_PVE_ID": "reader@pve!monitor", "TEST_PVE_SECRET": "PRIVATE-TOKEN"})
    @patch("portal.monitoring.requests.Session")
    def test_tls_error_does_not_expose_exception_or_credentials(self, session):
        session.return_value.get.side_effect = requests.exceptions.SSLError("PRIVATE-TOKEN")
        host = collect_host(CONFIG)
        self.assertEqual(host["state"], "unavailable")
        self.assertIn("TLS_VERIFICATION_FAILED", host["errors"])
        self.assertNotIn("PRIVATE-TOKEN", json.dumps(host))

    @patch("portal.monitoring.ProxmoxReader")
    def test_complete_inventory_and_backup_selection(self, reader):
        now = time.time()
        responses = {
            "/nodes/test-1/status": {"cpu": 0.2, "memory": {"used": 40, "total": 100}},
            "/nodes/test-1/storage": [{"storage": "nasbackup", "content": "backup", "active": 1}],
            "/nodes/test-1/qemu": [{"vmid": 1006, "name": "customer", "status": "running", "raw": "secret"},
                                  {"vmid": 1007, "name": "filtered", "status": "running"}],
            "/cluster/backup": [{"node": "test-1", "vmid": "100,200,300,400,1006,1007", "enabled": 1}],
            "/nodes/test-1/tasks": [{"status": "OK", "endtime": now, "starttime": now - 20}],
            "/nodes/test-1/storage/nasbackup/content": [{"vmid": 1006, "ctime": now}],
        }
        reader.return_value.get.side_effect = lambda path, **kwargs: responses[path]
        host = collect_host(CONFIG)
        self.assertEqual(host["state"], "connected")
        self.assertTrue(host["vms"][0]["selected"])
        self.assertEqual(host["vms"][0]["backup_at"], now)
        self.assertNotIn("secret", json.dumps(host))
        result = dashboard({"collected_at": now, "hosts": [host]})
        self.assertEqual(result["vms"][1]["backup_label"], "Not verified")
        self.assertEqual(result["backup_attention"], 0)
        responses["/nodes/test-1/storage/nasbackup/content"] = []
        empty_host = collect_host(CONFIG)
        empty_result = dashboard({"collected_at": now, "hosts": [empty_host]})
        self.assertEqual(empty_host["state"], "connected")
        self.assertTrue(all(vm["backup_label"] == "Not verified" for vm in empty_result["vms"]))
        self.assertEqual(empty_result["backup_attention"], 0)

    @patch("portal.monitoring.ProxmoxReader")
    def test_partial_failure_keeps_reachable_host_but_inventory_unknown(self, reader):
        def response(path, **kwargs):
            if path.endswith("/status"):
                return {"cpu": 0.3}
            raise MonitoringError("ACCESS_DENIED")
        reader.return_value.get.side_effect = response
        host = collect_host(CONFIG)
        self.assertEqual(host["state"], "partial")
        result = dashboard({"collected_at": time.time(), "hosts": [host]})
        self.assertFalse(result["inventory_complete"])
        self.assertEqual(result["connected"], 0)

    @override_settings(MONITORING_HOSTS_JSON="")
    def test_unconfigured_command_cannot_silently_claim_success(self):
        with self.assertRaises(CommandError):
            call_command("collect_monitoring")
