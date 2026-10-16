import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MonitoringTests(unittest.TestCase):
    def test_dashboards_only_reference_provisioned_datasources(self):
        provisioning = (ROOT / "grafana/provisioning/datasources/datasources.yaml").read_text()
        provisioned = set(re.findall(r"^\s+uid: (\S+)", provisioning, re.MULTILINE))
        builtins = {"-- Grafana --", "grafana", "__expr__"}
        for path in (ROOT / "grafana/dashboards").glob("*.json"):
            dashboard = json.loads(path.read_text())
            variables = {
                "${" + item["name"] + "}"
                for item in dashboard.get("templating", {}).get("list", [])
                if item.get("type") == "datasource"
            }

            def inspect(value):
                if isinstance(value, dict):
                    datasource = value.get("datasource")
                    if isinstance(datasource, dict):
                        self.assertIn(datasource["uid"], provisioned | builtins | variables,
                                      f"{path.name}: {datasource}")
                    for child in value.values():
                        inspect(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child)

            inspect(dashboard)

    def test_log_queries_match_collector_labels(self):
        alloy = (ROOT / "alloy/config.alloy").read_text()
        self.assertIn('loki.source.file "minecraft_logs"', alloy)
        self.assertNotIn("unix:///var/run/docker.sock", alloy)
        self.assertIn('job = "fabric-server_logs"', alloy)
        for path in (ROOT / "grafana/dashboards").glob("*Logging*.json"):
            text = path.read_text()
            self.assertNotIn('job=\\"minecraft\\"', text)


if __name__ == "__main__":
    unittest.main()
