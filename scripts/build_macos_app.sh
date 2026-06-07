#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="LeoJarvis"
VERSION="${LEOJARVIS_APP_VERSION:-0.1.0}"
ARCH="$(uname -m)"
DIST="${ROOT}/dist/macos"
APP="${DIST}/${APP_NAME}.app"
DMG="${DIST}/${APP_NAME}-${VERSION}-${ARCH}.dmg"
SWIFT_DIR="${ROOT}/desktop/macos"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/${APP_NAME}.build.XXXXXX")"
STAGING="${BUILD_ROOT}/staging"
APP_BUILD="${BUILD_ROOT}/${APP_NAME}.app"
DMG_BUILD="${BUILD_ROOT}/${APP_NAME}-${VERSION}-${ARCH}.dmg"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

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
rm -rf "${APP}" "${DMG}"
mkdir -p "${DIST}" "${APP_BUILD}/Contents/MacOS" "${APP_BUILD}/Contents/Resources" "${STAGING}"
install -m 755 "${BIN}" "${APP_BUILD}/Contents/MacOS/${APP_NAME}"
chmod +x "${APP_BUILD}/Contents/MacOS/${APP_NAME}"

if [[ -f "${ROOT}/web/public/brand-mark.png" ]]; then
  ditto --norsrc --noextattr "${ROOT}/web/public/brand-mark.png" "${APP_BUILD}/Contents/Resources/brand-mark.png"
fi

if [[ -f "${ROOT}/web/public/app-icon.png" ]]; then
  ditto --norsrc --noextattr "${ROOT}/web/public/app-icon.png" "${APP_BUILD}/Contents/Resources/app-icon.png"
  ICONSET="${STAGING}/${APP_NAME}.iconset"
  rm -rf "${ICONSET}"
  mkdir -p "${ICONSET}"
  sips -z 16 16 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_16x16.png" >/dev/null
  sips -z 32 32 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_32x32.png" >/dev/null
  sips -z 64 64 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_128x128.png" >/dev/null
  sips -z 256 256 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_256x256.png" >/dev/null
  sips -z 512 512 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "${ROOT}/web/public/app-icon.png" --out "${ICONSET}/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "${ICONSET}" -o "${APP_BUILD}/Contents/Resources/LeoJarvis.icns"
  rm -rf "${ICONSET}"
fi

INFO="${APP_BUILD}/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Clear dict" "${INFO}" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.leo.leojarvis.desktop" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string ${APP_NAME}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string LeoJarvis" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundlePackageType string APPL" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true" "${INFO}"
/usr/libexec/PlistBuddy -c "Add :NSUserNotificationAlertStyle string alert" "${INFO}"

echo "==> Clean metadata and sign app"
xattr -cr "${APP_BUILD}" 2>/dev/null || true
find "${APP_BUILD}" -print0 | xargs -0 xattr -c 2>/dev/null || true
find "${APP_BUILD}" -name "._*" -delete
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "${APP_BUILD}" >/dev/null
  codesign --verify --deep --strict "${APP_BUILD}" >/dev/null
fi

echo "==> Create DMG"
ditto --norsrc --noextattr "${APP_BUILD}" "${STAGING}/${APP_NAME}.app"
if [[ -f "${APP_BUILD}/Contents/Resources/LeoJarvis.icns" ]]; then
  ditto --norsrc --noextattr "${APP_BUILD}/Contents/Resources/LeoJarvis.icns" "${STAGING}/.VolumeIcon.icns"
  if command -v SetFile >/dev/null 2>&1; then
    SetFile -a C "${STAGING}" || true
  fi
fi
ln -s /Applications "${STAGING}/Applications"
hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGING}" -ov -format UDZO "${DMG_BUILD}"
xattr -cr "${APP_BUILD}" 2>/dev/null || true
find "${APP_BUILD}" -print0 | xargs -0 xattr -c 2>/dev/null || true
find "${APP_BUILD}" -name "._*" -delete
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "${APP_BUILD}" >/dev/null
  codesign --verify --deep --strict "${APP_BUILD}" >/dev/null
fi
ditto --norsrc --noextattr "${APP_BUILD}" "${APP}"
xattr -cr "${APP}" 2>/dev/null || true
find "${APP}" -print0 | xargs -0 xattr -c 2>/dev/null || true
find "${APP}" -name "._*" -delete
# Desktop/File Provider folders can re-add FinderInfo to .app bundles after copy.
# The canonical signed artifact is verified above in the temp build folder and
# again when packaged into the DMG.
ditto --norsrc --noextattr "${DMG_BUILD}" "${DMG}"
xattr -c "${DMG}" 2>/dev/null || true
if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - "${DMG}" >/dev/null
  codesign --verify "${DMG}" >/dev/null
fi

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
