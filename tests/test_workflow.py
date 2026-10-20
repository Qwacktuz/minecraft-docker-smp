import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/deploy.yml"


def step_script(name, field):
    step = WORKFLOW.read_text().split(f"      - name: {name}\n", 1)[1]
    step = step.split("\n      - name:", 1)[0]
    return textwrap.dedent(step.split(f"{field}: |\n", 1)[1])


MOCK = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if name == "timeout":
    if os.environ.get("LOOKUP_FAIL"):
        print("peer lookup failed", file=sys.stderr)
        sys.exit(124)
    os.execvp(args[1], args[1:])
if name == "tailscale":
    if args == ["status"]:
        print("diagnostic peer status")
    else:
        assert args == ["ip", "-4", "mc-prod"], args
        marker = Path(os.environ["MOCK_LOG"] + ".attempted")
        if not marker.exists():
            marker.touch()
            print("no matching peer: mc-prod", file=sys.stderr)
            sys.exit(1)
        print("100.100.1.2")
'''


class WorkflowTests(unittest.TestCase):
    def run_step(self, name, field, *, lookup_fail=False, existing_checkout=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "bin"
            binary.mkdir()
            for command in ("tailscale", "timeout", "sleep", "sudo", "flock", "git"):
                path = binary / command
                path.write_text(f"#!{sys.executable}\n" + MOCK)
                path.chmod(0o755)
            if name == "Deploy via SSH":
                app = root / "app"
                app.mkdir()
                if existing_checkout:
                    (app / ".git").mkdir()
                (app / "scripts").mkdir()
                (app / "scripts/deploy.sh").write_text("echo deployment-script-ran\n")
            log = root / "calls.jsonl"
            github_env = root / "github-env"
            env = dict(os.environ, TS_HOST="mc-prod",
                       DEPLOY_SHA="a" * 40,
                       DEPLOY_REPO="https://github.com/Qwacktuz/minecraft-docker-smp.git",
                       GITHUB_ENV=str(github_env), MOCK_LOG=str(log),
                       PATH=f"{binary}:{os.environ['PATH']}")
            if lookup_fail:
                env["LOOKUP_FAIL"] = "1"
            script = step_script(name, field)
            # Redirect deployment files and the lock into the test sandbox.
            script = script.replace("$HOME/", f"{root}/")
            result = subprocess.run(["bash", "-e", "-c", script],
                                    env=env, capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            output = github_env.read_text() if github_env.exists() else ""
            return result, calls, output

    def test_lookup_retries_reports_error_and_exports_resolved_ip(self):
        result, calls, output = self.run_step("Resolve Server Tailscale IP", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no matching peer: mc-prod", result.stderr)
        self.assertEqual(output, "TS_IP=100.100.1.2\n")
        self.assertEqual(sum(call[0] == "tailscale" for call in calls), 2)

    def test_lookup_timeout_fails_with_diagnostics_and_no_ip(self):
        result, calls, output = self.run_step("Resolve Server Tailscale IP", "run",
                                              lookup_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("peer lookup failed", result.stderr)
        self.assertIn("::error::Could not resolve mc-prod", result.stdout)
        self.assertIn("diagnostic peer status", result.stdout)
        self.assertIn(["tailscale", "status"], calls)
        self.assertEqual(output, "")

    def test_deployment_uses_current_repository_for_new_and_existing_checkouts(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                result, calls, _ = self.run_step("Deploy via SSH", "script",
                                                  existing_checkout=existing)
                self.assertEqual(result.returncode, 0, result.stderr)
                repo = "https://github.com/Qwacktuz/minecraft-docker-smp.git"
                clone = ["git", "clone", repo, "."]
                self.assertEqual(clone in calls, not existing)
                update = ["git", "remote", "set-url", "origin", repo]
                fetch = ["git", "fetch", "origin", "a" * 40]
                self.assertLess(calls.index(update), calls.index(fetch))
                self.assertIn(["git", "reset", "--hard", "a" * 40], calls)
                self.assertIn("deployment-script-ran", result.stdout)


if __name__ == "__main__":
    unittest.main()
