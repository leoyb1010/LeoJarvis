#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SIM="$("$ROOT/ios/CortexFleet/scripts/select-simulator.sh" "${1:-iPhone 17 Pro Max}")"
DERIVED="${DERIVED_DATA_PATH:-/tmp/CortexFleetDerived}"
PROJECT="$ROOT/ios/CortexFleet/CortexFleet.xcodeproj"
APP="$DERIVED/Build/Products/Debug-iphonesimulator/CortexFleet.app"

xcrun simctl boot "$SIM" 2>/dev/null || true
xcrun simctl bootstatus "$SIM" -b

rm -rf "$DERIVED"
xcodebuild -quiet \
  -project "$PROJECT" \
  -scheme CortexFleet \
  -destination "platform=iOS Simulator,id=$SIM" \
  -derivedDataPath "$DERIVED" \
  build

xcrun simctl install "$SIM" "$APP"
xcrun simctl launch "$SIM" com.leo.cortexfleet
echo "$SIM"
