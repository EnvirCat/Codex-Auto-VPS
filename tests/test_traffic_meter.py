import http.client
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.traffic_meter import Config, MeterHTTPServer, UsageMeter, billing_cycle_start


class MeterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.subscription_dir = self.root / "private" / "abc123"
        self.subscription_dir.mkdir(parents=True)
        self.clash_body = b"proxies: []\n"
        self.hiddify_body = b"hysteria2://example.invalid\n"
        (self.subscription_dir / "clash.yaml").write_bytes(self.clash_body)
        (self.subscription_dir / "hiddify.txt").write_bytes(self.hiddify_body)
        (self.subscription_dir / "clash.yaml.new").write_bytes(b"must not be served")
        self.counter_values = [1000, 2000]
        self.boot_value = ["boot-a"]
        self.config = Config(
            bind="127.0.0.1",
            port=0,
            interface="eth0",
            static_root=self.root,
            allowed_paths=frozenset(
                {"/private/abc123/clash.yaml", "/private/abc123/hiddify.txt"}
            ),
            state_file=self.root / "state" / "usage.json",
            quota_bytes=1_000_000,
            initial_upload_bytes=0,
            initial_download_bytes=123_000,
            reset_day=26,
            timezone=ZoneInfo("America/Manaus"),
            expire_epoch=1_234_567_890,
            poll_seconds=1,
        )

    def tearDown(self):
        self.temp.cleanup()

    def counter_reader(self, _interface):
        return tuple(self.counter_values)

    def boot_reader(self):
        return self.boot_value[0]

    def new_meter(self):
        return UsageMeter(
            self.config,
            counter_reader=self.counter_reader,
            boot_id_reader=self.boot_reader,
        )

    def test_cycle_uses_last_month_before_reset_and_current_month_after(self):
        zone = ZoneInfo("America/Manaus")
        before = datetime(2026, 9, 25, 23, 59, tzinfo=zone)
        after = datetime(2026, 9, 26, 0, 0, tzinfo=zone)
        self.assertEqual(billing_cycle_start(before, 26).date().isoformat(), "2026-08-26")
        self.assertEqual(billing_cycle_start(after, 26).date().isoformat(), "2026-09-26")

    def test_seeds_provider_usage_then_accumulates_interface_deltas(self):
        meter = self.new_meter()
        first = meter.sample(datetime(2026, 9, 28, 10, 0, tzinfo=self.config.timezone))
        self.assertEqual(first["upload"], 0)
        self.assertEqual(first["download"], 123_000)

        self.counter_values[:] = [1500, 2800]
        second = meter.sample(datetime(2026, 9, 28, 10, 1, tzinfo=self.config.timezone))
        self.assertEqual(second["upload"], 500)
        self.assertEqual(second["download"], 123_800)
        self.assertEqual(second["total"], 1_000_000)

    def test_reboot_counter_reset_preserves_accumulated_usage(self):
        meter = self.new_meter()
        first = meter.sample(datetime(2026, 9, 28, 10, 0, tzinfo=self.config.timezone))
        self.counter_values[:] = [50, 60]
        self.boot_value[0] = "boot-b"
        second = meter.sample(datetime(2026, 9, 28, 10, 1, tzinfo=self.config.timezone))
        self.assertEqual(second["upload"], first["upload"] + 50)
        self.assertEqual(second["download"], first["download"] + 60)

    def test_monthly_boundary_resets_counters_without_reapplying_seed(self):
        meter = self.new_meter()
        before = meter.sample(datetime(2026, 9, 25, 23, 59, tzinfo=self.config.timezone))
        self.counter_values[:] = [1200, 2300]
        after = meter.sample(datetime(2026, 9, 26, 0, 0, tzinfo=self.config.timezone))
        self.assertGreater(before["download"], 0)
        self.assertEqual(after["upload"], 0)
        self.assertEqual(after["download"], 0)

    def test_http_server_serves_only_allowlisted_files_and_usage_header(self):
        meter = self.new_meter()
        meter.sample(datetime(2026, 9, 28, 10, 0, tzinfo=self.config.timezone))
        server = MeterHTTPServer(("127.0.0.1", 0), self.config, meter)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/private/abc123/clash.yaml")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), self.clash_body)
            metadata = response.getheader("Subscription-Userinfo", "")
            fields = dict(part.strip().split("=", 1) for part in metadata.split(";"))
            self.assertEqual(fields["download"], "123000")
            self.assertEqual(fields["total"], "1000000")
            self.assertEqual(fields["expire"], str(self.config.expire_epoch))
            connection.close()

            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/private/abc123/clash.yaml.new")
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            connection.close()

            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("HEAD", "/private/abc123/hiddify.txt")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(int(response.getheader("Content-Length", "0")), len(self.hiddify_body))
            self.assertIn("total=1000000", response.getheader("Subscription-Userinfo", ""))
            self.assertEqual(response.read(), b"")
            connection.close()

            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/private/abc123/%2e%2e/clash.yaml")
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
