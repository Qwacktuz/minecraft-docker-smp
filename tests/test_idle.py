"""scripts/idle_check.py: the auto-stop decision and the player-count ping."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import idle_check  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/idle_check.py"
HOUR = 3600


class Decide(unittest.TestCase):
    def test_players_keep_it_running(self):
        state = {"up_since": 0, "last_busy": 0}
        stop, _ = idle_check.decide(state, 1, 10 * HOUR, 120, 7)
        self.assertFalse(stop)
        self.assertEqual(state["last_busy"], 10 * HOUR)

    def test_stops_after_two_idle_hours(self):
        state = {"up_since": 0, "last_busy": 0}
        self.assertFalse(idle_check.decide(state, 0, 2 * HOUR - 60, 120, 7)[0])
        self.assertTrue(idle_check.decide(state, 0, 2 * HOUR, 120, 7)[0])

    def test_no_answer_counts_as_idle(self):
        state = {"up_since": 0, "last_busy": 0}
        self.assertTrue(idle_check.decide(state, None, 2 * HOUR, 120, 7)[0])

    def test_first_sight_starts_the_clock(self):
        state = {}
        self.assertFalse(idle_check.decide(state, 0, 100, 120, 7)[0])
        self.assertEqual(state, {"up_since": 100, "last_busy": 100})

    def test_cap_stops_even_with_players(self):
        state = {"up_since": 0, "last_busy": 0}
        stop, reason = idle_check.decide(state, 3, 7 * 24 * HOUR, 120, 7)
        self.assertTrue(stop)
        self.assertIn("cap", reason)


def fake_server(online):
    """A one-shot Minecraft status responder on localhost. Returns the port."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        conn, _ = listener.accept()
        with conn, listener:
            idle_check.read_exact(conn, idle_check.read_varint(conn))  # handshake
            idle_check.read_exact(conn, idle_check.read_varint(conn))  # status request
            body = json.dumps({"players": {"online": online, "max": 20}}).encode()
            packet = idle_check.varint(0) + idle_check.varint(len(body)) + body
            conn.sendall(idle_check.varint(len(packet)) + packet)

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


class Ping(unittest.TestCase):
    def test_reads_the_player_count(self):
        port = fake_server(2)
        self.assertEqual(idle_check.players_online("127.0.0.1", "localhost", port), 2)


class Cli(unittest.TestCase):
    def run_check(self, state, port, host="localhost"):
        with tempfile.TemporaryDirectory() as tmp:
            path, output = Path(tmp, "state.json"), Path(tmp, "out")
            if state is not None:
                path.write_text(json.dumps(state))
            env = dict(os.environ, GITHUB_OUTPUT=str(output))
            result = subprocess.run(
                [sys.executable, SCRIPT, "--state", path, "--host", host, "--port", str(port)],
                env=env, capture_output=True, text=True, check=True)
            return result.stdout, output.read_text(), json.loads(path.read_text())

    def test_long_idle_server_is_stopped(self):
        three_hours_ago = int(time.time()) - 3 * HOUR
        state = {"address": "127.0.0.1", "up_since": three_hours_ago, "last_busy": three_hours_ago}
        stdout, output, _ = self.run_check(state, fake_server(0))
        self.assertEqual(output, "stop=true\n")
        self.assertIn("nobody online", stdout)

    def test_bot_online_keeps_it(self):
        three_hours_ago = int(time.time()) - 3 * HOUR
        state = {"address": "127.0.0.1", "up_since": three_hours_ago, "last_busy": three_hours_ago}
        _, output, state = self.run_check(state, fake_server(1))
        self.assertEqual(output, "stop=false\n")
        self.assertGreater(state["last_busy"], three_hours_ago)

    def test_new_vps_starts_fresh(self):
        state = {"address": "192.0.2.1", "up_since": 0, "last_busy": 0}
        _, output, state = self.run_check(state, fake_server(0))
        self.assertEqual(output, "stop=false\n")
        self.assertEqual(state["address"], "127.0.0.1")
        self.assertGreater(state["up_since"], 0)

    def test_no_dns_record_resets_the_state(self):
        _, output, state = self.run_check({"up_since": 0, "last_busy": 0}, 1, host="no-such-host.invalid")
        self.assertEqual(output, "stop=false\n")
        self.assertEqual(state, {})


if __name__ == "__main__":
    unittest.main()
