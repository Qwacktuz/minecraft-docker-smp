import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/tailscale-device.py"
SPEC = importlib.util.spec_from_file_location("tailscale_device", SCRIPT)
DEVICE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVICE)


class TailscaleDeviceTests(unittest.TestCase):
    def token_response(self):
        return io.BytesIO(json.dumps({"access_token": "test-token"}).encode())

    def devices_response(self, *devices):
        return io.BytesIO(json.dumps({"devices": devices}).encode())

    def device(self, **overrides):
        return dict({
            "hostname": "mc-prod", "authorized": True, "tags": ["tag:server"],
            "addresses": ["100.100.1.2", "fd7a:115c:a1e0::1"],
        }, **overrides)

    def test_enrollment_waits_for_exact_server_and_accepts_registered_device(self):
        with patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
            self.token_response(), self.devices_response(self.device(hostname="mc-prod-old")),
            self.devices_response(self.device()),
        ]) as request, patch.object(DEVICE.time, "sleep") as sleep, \
                patch("sys.stdout", new_callable=io.StringIO):
            DEVICE.wait_for_device("mc-prod", "test-tailnet", "test-client", "test-secret")
        sleep.assert_called_once_with(10)
        self.assertEqual(request.call_args.args[0].full_url,
                         DEVICE.API + "/tailnet/test-tailnet/devices?fields=all")

    def test_enrollment_rejects_ambiguous_or_untrusted_registration(self):
        cases = [
            [self.device(), self.device()],
            [self.device(authorized=False)],
            [self.device(tags=["tag:ci"])],
            [self.device(addresses=["192.0.2.1"])],
        ]
        for devices in cases:
            with self.subTest(devices=devices), patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
                self.token_response(), self.devices_response(*devices),
            ]), patch("sys.stdout", new_callable=io.StringIO), self.assertRaises(ValueError):
                DEVICE.wait_for_device("mc-prod", "test-tailnet", "test-client", "test-secret")

    def test_missing_existing_server_has_bounded_wait_and_recovery_message(self):
        with patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
            self.token_response(), self.devices_response(),
        ]), patch.object(DEVICE.time, "sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaisesRegex(ValueError, "needs host re-enrollment"):
                DEVICE.wait_for_device("mc-prod", "test-tailnet", "test-client", "test-secret", timeout=0)
            sleep.assert_not_called()

    def test_deletes_only_recorded_node_id(self):
        with patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
            self.token_response(), io.BytesIO(b""),
        ]) as request, patch("sys.stdout", new_callable=io.StringIO) as output:
            DEVICE.delete_device("node-id", "test-client", "test-secret")
        token_request, delete_request = [call.args[0] for call in request.call_args_list]
        self.assertEqual(token_request.full_url, DEVICE.API + "/oauth/token")
        form = urllib.parse.parse_qs(token_request.data.decode())
        self.assertEqual(form["scope"], ["devices:core"])
        self.assertEqual(form["client_secret"], ["test-secret"])
        self.assertEqual(delete_request.full_url, DEVICE.API + "/device/node-id")
        self.assertEqual(delete_request.method, "DELETE")
        self.assertEqual(delete_request.get_header("Authorization"), "Bearer test-token")
        self.assertNotIn("test-secret", output.getvalue())
        self.assertNotIn("test-token", output.getvalue())

    def test_already_deleted_device_is_successful(self):
        with patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
            self.token_response(), urllib.error.HTTPError("url", 404, "missing", {}, None),
        ]), patch("sys.stdout", new_callable=io.StringIO):
            DEVICE.delete_device("node-id", "test-client", "test-secret")

    def test_cleanup_errors_are_not_silenced(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status), patch.object(DEVICE.urllib.request, "urlopen", side_effect=[
                self.token_response(), urllib.error.HTTPError("url", status, "error", {}, None),
            ]), self.assertRaises(urllib.error.HTTPError):
                DEVICE.delete_device("node-id", "test-client", "test-secret")

    def test_bad_oauth_credentials_prevent_deletion(self):
        with patch.object(DEVICE.urllib.request, "urlopen", side_effect=
                          urllib.error.HTTPError("url", 401, "denied", {}, None)) as request:
            with self.assertRaises(urllib.error.HTTPError):
                DEVICE.delete_device("node-id", "test-client", "test-secret")
            self.assertEqual(request.call_count, 1)

    def test_missing_credentials_fail_before_network_access(self):
        with patch.dict(DEVICE.os.environ, {}, clear=True), patch.object(DEVICE.sys, "argv", [str(SCRIPT), "delete"]), \
                patch.object(DEVICE.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "TF_VAR_ts_oauth_client_secret"):
                DEVICE.main()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
