#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SIM="${1:-$("$ROOT/ios/CortexFleet/scripts/select-simulator.sh")}"

cleanup_serve_sim() {
  npx --yes serve-sim@latest --kill "$SIM" >/dev/null 2>&1 || true
}

trap cleanup_serve_sim EXIT INT TERM HUP
cleanup_serve_sim

echo "Starting simulator mirror for $SIM"
echo "Open the local URL printed below in the Codex in-app browser."
npx --yes serve-sim@latest "$SIM"
