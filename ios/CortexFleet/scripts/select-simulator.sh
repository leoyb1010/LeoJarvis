#!/usr/bin/env bash
set -euo pipefail

PREFERRED_NAME="${1:-iPhone 17 Pro Max}"

python3 - "$PREFERRED_NAME" <<'PY'
import json
import subprocess
import sys

preferred = sys.argv[1]
raw = subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"], text=True)
data = json.loads(raw)
devices = [d for rows in data.get("devices", {}).values() for d in rows if d.get("isAvailable")]

booted = [d for d in devices if d.get("state") == "Booted"]
if booted:
    print(booted[0]["udid"])
    sys.exit(0)

def score(device):
    name = device.get("name", "")
    if name == preferred:
        return 0
    if "iPhone 17 Pro Max" in name:
        return 1
    if "iPhone 17 Pro" in name:
        return 2
    if name.startswith("iPhone"):
        return 3
    if name.startswith("iPad"):
        return 4
    return 5

if not devices:
    raise SystemExit("No available iOS simulators found.")

devices.sort(key=score)
print(devices[0]["udid"])
PY
