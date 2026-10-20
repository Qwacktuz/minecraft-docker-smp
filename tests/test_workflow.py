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
    lines = step.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"{field}: |")
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return textwrap.dedent("\n".join(block))


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
        print("peer unreachable", file=sys.stderr)
        sys.exit(124)
    os.execvp(args[1], args[1:])
if name == "tailscale":
    if args == ["status"]:
        print("diagnostic peer status")
    else:
        assert args == ["ping", "--timeout=5s", "--c=1", "100.100.1.2"], args
        marker = Path(os.environ["MOCK_LOG"] + ".attempted")
        if not marker.exists():
            marker.touch()
            print("peer unreachable", file=sys.stderr)
            sys.exit(1)
        print("pong")
if name == "tofu":
    if args[0] == os.environ.get("FAIL_TOFU_STAGE"):
        sys.exit(1)
    if args == ["output", "-raw", "tailscale_ipv4"]:
        print("100.100.1.2", end="")
'''


class WorkflowTests(unittest.TestCase):
    def run_step(self, name, field, *, lookup_fail=False, existing_checkout=False,
                 operation="apply", confirmation="", fail_tofu_stage=""):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "bin"
            binary.mkdir()
            for command in ("tailscale", "timeout", "sleep", "sudo", "flock", "git", "tofu"):
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
            env = dict(os.environ, TS_IP="100.100.1.2",
                       OPERATION=operation, DESTROY_CONFIRMATION=confirmation,
                       FAIL_TOFU_STAGE=fail_tofu_stage,
                       TF_VAR_server_name="mc-prod", R2_BUCKET_NAME="dummy", R2_ENDPOINT="dummy",
                       DEPLOY_SHA="a" * 40,
                       DEPLOY_REPO="https://github.com/Qwacktuz/minecraft-docker-smp.git",
                       GITHUB_ENV=str(github_env), GITHUB_OUTPUT=str(github_env), MOCK_LOG=str(log),
                       PATH=f"{binary}:{os.environ['PATH']}")
            if lookup_fail:
                env["LOOKUP_FAIL"] = "1"
            script = step_script(name, field)
            # Redirect deployment files and the lock into the test sandbox.
            script = script.replace("$HOME/", f"{root}/")
            result = subprocess.run(["bash", "-e", "-c", script],
                                    env=env, capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            output = github_env.read_text() if github_env.exists() else ""
            return result, calls, output

    def test_connectivity_retries_without_dns_and_exports_registered_ip(self):
        result, calls, output = self.run_step("Wait for Server Tailscale Connectivity", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("peer unreachable", result.stderr)
        self.assertEqual(output, "TS_IP=100.100.1.2\n")
        self.assertEqual(sum(call[0] == "tailscale" for call in calls), 2)

    def test_connectivity_timeout_fails_with_diagnostics_and_no_ip(self):
        result, calls, output = self.run_step("Wait for Server Tailscale Connectivity", "run",
                                              lookup_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("peer unreachable", result.stderr)
        self.assertIn("::error::Registered Minecraft device is unreachable", result.stdout)
        self.assertIn("diagnostic peer status", result.stdout)
        self.assertIn(["tailscale", "status"], calls)
        self.assertEqual(output, "")

    def test_apply_publishes_registered_address_after_apply(self):
        result, calls, output = self.run_step("OpenTofu Init and Lifecycle", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "tailscale_ipv4=100.100.1.2\n")
        self.assertEqual([call[1] for call in calls], ["init", "apply", "output"])

    def test_destroy_requires_hostname_confirmation_before_any_tofu_command(self):
        result, calls, output = self.run_step("OpenTofu Init and Lifecycle", "run",
                                              operation="destroy", confirmation="wrong-server")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertEqual(output, "")

    def test_infrastructure_failures_do_not_publish_an_address(self):
        for stage in ("init", "apply", "output", "destroy"):
            with self.subTest(stage=stage):
                result, _, output = self.run_step(
                    "OpenTofu Init and Lifecycle", "run", fail_tofu_stage=stage,
                    operation="destroy" if stage == "destroy" else "apply",
                    confirmation="mc-prod",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")

    def test_confirmed_destroy_does_not_apply_or_publish_address(self):
        result, calls, output = self.run_step("OpenTofu Init and Lifecycle", "run",
                                              operation="destroy", confirmation="mc-prod")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[1] for call in calls], ["init", "destroy"])
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
