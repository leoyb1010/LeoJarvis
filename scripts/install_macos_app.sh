#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="LeoJarvis.app"
CANONICAL="/Applications/${APP_NAME}"

bash "${ROOT}/scripts/build_macos_app.sh"

osascript -e 'tell application "LeoJarvis" to quit' >/dev/null 2>&1 || true

rm -rf "${CANONICAL}"
ditto --norsrc --noextattr "${ROOT}/dist/macos/${APP_NAME}" "${CANONICAL}"
xattr -cr "${CANONICAL}" 2>/dev/null || true
find "${CANONICAL}" -print0 | xargs -0 xattr -c 2>/dev/null || true
find "${CANONICAL}" -name "._*" -delete
codesign --verify --deep --strict "${CANONICAL}"

# Keep only the canonical installed app. The dist build artifact is retained for DMG packaging.
for base in "${HOME}/Applications" "${HOME}/Desktop" "${HOME}/Downloads"; do
  [[ -d "${base}" ]] || continue
  find "${base}" -maxdepth 3 \( \
    -name "LeoJarvis.app" -o \
    -name "Cortex.app" -o \
    -name "CortexFleet.app" -o \
    -name "Cortex Fleet.app" \
  \) -prune -exec rm -rf {} + 2>/dev/null || true
done

echo "Installed: ${CANONICAL}"
echo "Remaining installed apps:"
SEARCH_BASES=("/Applications")
for base in "${HOME}/Applications" "${HOME}/Desktop" "${HOME}/Downloads"; do
  [[ -d "${base}" ]] && SEARCH_BASES+=("${base}")
done
find "${SEARCH_BASES[@]}" -maxdepth 3 \( \
  -name "LeoJarvis.app" -o \
  -name "Cortex.app" -o \
  -name "CortexFleet.app" -o \
  -name "Cortex Fleet.app" \
\) -print 2>/dev/null || true
