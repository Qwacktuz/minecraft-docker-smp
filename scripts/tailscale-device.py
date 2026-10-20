#!/usr/bin/env python3
"""Observe server enrollment and delete the exact node owned by OpenTofu."""

import ipaddress
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.tailscale.com/api/v2"


def access_token(client_id, client_secret):
    # Never print request bodies, tokens, or API error bodies: these can contain
    # credentials. Use the default TLS trust configuration for every request.
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "devices:core",
    }).encode()
    request = urllib.request.Request(f"{API}/oauth/token", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def wait_for_device(hostname, tailnet, client_id, client_secret, timeout=900):
    token = access_token(client_id, client_secret)
    tailnet_path = urllib.parse.quote(tailnet, safe="")
    request = urllib.request.Request(
        f"{API}/tailnet/{tailnet_path}/devices?fields=all",
        headers={"Authorization": f"Bearer {token}"},
    )
    deadline = time.monotonic() + timeout
    print("Waiting for the Minecraft VPS to enroll in Tailscale...", flush=True)
    while True:
        with urllib.request.urlopen(request, timeout=30) as response:
            matches = [
                device for device in json.load(response)["devices"]
                if device.get("hostname") == hostname
            ]
        if len(matches) > 1:
            raise ValueError("Multiple Tailscale devices have the server hostname; resolve the conflict.")
        if matches:
            device = matches[0]
            if not device.get("authorized") or "tag:server" not in device.get("tags", []):
                raise ValueError("The server device must be authorized and tagged tag:server.")
            addresses = [
                address for address in device.get("addresses", [])
                if ipaddress.ip_address(address) in ipaddress.ip_network("100.64.0.0/10")
            ]
            if len(addresses) != 1:
                raise ValueError("The server device must have exactly one Tailscale IPv4 address.")
            print("Minecraft device registered; OpenTofu will record its node ID.")
            return
        if time.monotonic() >= deadline:
            raise ValueError(
                "Server did not enroll within the registration timeout. "
                "Inspect cloud-init for a new VPS. An existing VPS absent from "
                "Tailscale needs host re-enrollment; generating another key "
                "does not rerun cloud-init or replace the VPS."
            )
        time.sleep(10)


def delete_device(device_id, client_id, client_secret):
    token = access_token(client_id, client_secret)
    device_path = urllib.parse.quote(device_id, safe="")
    request = urllib.request.Request(
        f"{API}/device/{device_path}", method="DELETE",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    print("Managed Tailscale device removed (or already absent).")


def main():
    if sys.argv[1:] not in (["delete"], ["wait"]):
        raise ValueError("Usage: tailscale-device.py wait|delete")
    operation = sys.argv[1]
    names = (
        ("TS_DEVICE_ID",) if operation == "delete" else ("TS_HOST", "TS_TAILNET")
    ) + ("TF_VAR_ts_oauth_client_id", "TF_VAR_ts_oauth_client_secret")
    values = [os.environ.get(name, "") for name in names]
    missing = [name for name, value in zip(names, values) if not value.strip()]
    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))
    if operation == "delete":
        delete_device(*values)
    else:
        wait_for_device(*values)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print(f"Tailscale API returned HTTP {error.code}; check OAuth devices:core permissions.",
              file=sys.stderr)
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError):
        print("Could not reach the Tailscale API; retry the operation.", file=sys.stderr)
        sys.exit(1)
    except (json.JSONDecodeError, KeyError):
        print("Invalid Tailscale API response.", file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
