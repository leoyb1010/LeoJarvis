#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="LeoJarvis"
VERSION="${LEOJARVIS_APP_VERSION:-0.1.0}"
ARCH="$(uname -m)"
DIST="${ROOT}/dist/macos"
STAGING="${DIST}/staging"
APP="${DIST}/${APP_NAME}.app"
DMG="${DIST}/${APP_NAME}-${VERSION}-${ARCH}.dmg"
SWIFT_DIR="${ROOT}/desktop/macos"

export PATH="${HOME}/.nvm/versions/node/v24.15.0/bin:${HOME}/.volta/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js or set PATH before running this script." >&2
  exit 127
fi

echo "==> Build web assets"
(cd "${ROOT}/web" && npm run build)

echo "==> Build macOS desktop binary"
(cd "${SWIFT_DIR}" && swift build -c release)

BIN="${SWIFT_DIR}/.build/release/LeoJarvisDesktop"
if [[ ! -x "${BIN}" ]]; then
  echo "Missing Swift binary: ${BIN}" >&2
  exit 1
fi

echo "==> Assemble ${APP_NAME}.app"
rm -rf "${APP}" "${STAGING}" "${DMG}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources" "${STAGING}"
cp "${BIN}" "${APP}/Contents/MacOS/${APP_NAME}"
chmod +x "${APP}/Contents/MacOS/${APP_NAME}"

if [[ -f "${ROOT}/web/public/brand-mark.png" ]]; then
  cp "${ROOT}/web/public/brand-mark.png" "${APP}/Contents/Resources/brand-mark.png"
fi

INFO="${APP}/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Clear dict" "${INFO}" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.leo.leojarvis.desktop" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundlePackageType string APPL" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSUserNotificationAlertStyle string alert" "${INFO}"

echo "==> Create DMG"
cp -R "${APP}" "${STAGING}/${APP_NAME}.app"
ln -s /Applications "${STAGING}/Applications"
hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGING}" -ov -format UDZO "${DMG}"

SHA="$(shasum -a 256 "${DMG}" | awk '{print $1}')"
MANIFEST="${ROOT}/desktop/updates/appcast.json"
cat > "${MANIFEST}" <<EOF
{
  "version": "${VERSION}",
  "notes": "LeoJarvis macOS App local build.",
  "dmg_url": "file://${DMG}",
  "sha256": "${SHA}"
}
EOF

echo "==> Done"
echo "App: ${APP}"
echo "DMG: ${DMG}"
echo "SHA256: ${SHA}"
