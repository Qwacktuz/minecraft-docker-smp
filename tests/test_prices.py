"""Every server type bin/server may create has an hourly price for the web app.

Hetzner prices differ per type, and the watchdog counts uptime per type. The
admin page's cost estimate multiplies each type's hours by its price in
web/wrangler.toml ([vars.HOURLY_PRICES_EUR]); a type bin/server can fall back to
without a price would silently drop out of the estimate.
"""

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def server_types():
    """The default SERVER_TYPES in bin/server, in order."""
    match = re.search(r'^SERVER_TYPES=\$\{SERVER_TYPES:-([^}]*)\}', (ROOT / "bin/server").read_text(), re.M)
    if not match:
        raise AssertionError("no SERVER_TYPES default in bin/server")
    return match.group(1).split()


def hourly_prices():
    config = tomllib.loads((ROOT / "web/wrangler.toml").read_text())
    return config.get("vars", {}).get("HOURLY_PRICES_EUR")


class PricesTest(unittest.TestCase):
    def test_prices_are_a_table(self):
        self.assertIsInstance(hourly_prices(), dict, "web/wrangler.toml needs a [vars.HOURLY_PRICES_EUR] table")

    def test_every_server_type_has_a_price(self):
        prices = hourly_prices() or {}
        types = server_types()
        self.assertTrue(types)
        for server_type in types:
            with self.subTest(server_type=server_type):
                self.assertIn(server_type, prices,
                              f"{server_type} is in SERVER_TYPES (bin/server) but has no price in "
                              "[vars.HOURLY_PRICES_EUR] (web/wrangler.toml)")

    def test_prices_are_plausible_euros_per_hour(self):
        # Positive numbers (TOML floats or integers), and per hour, not per month:
        # a Hetzner cloud server costs cents an hour.
        for server_type, price in (hourly_prices() or {}).items():
            with self.subTest(server_type=server_type):
                self.assertRegex(server_type, r"^[a-z0-9]+$")
                self.assertIsInstance(price, (int, float), f"{server_type}: the price must be a number")
                self.assertNotIsInstance(price, bool)
                self.assertGreater(price, 0, f"{server_type}: set its hourly price from the Hetzner console")
                self.assertLess(price, 1, f"{server_type}: {price} €/h looks like a monthly price")


if __name__ == "__main__":
    unittest.main()
