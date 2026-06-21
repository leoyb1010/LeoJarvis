#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHISPER_ROOT="${LEOJARVIS_WHISPER_DIR:-${HOME}/Library/Application Support/LeoJarvis/whisper}"
REPO="${LEOJARVIS_WHISPER_CPP_DIR:-${WHISPER_ROOT}/whisper.cpp}"
MODEL_DIR="${LEOJARVIS_WHISPER_MODEL_DIR:-${WHISPER_ROOT}/models}"
MODEL="${1:-base}"

case "${MODEL}" in
  tiny|base|small|all) ;;
  *) echo "Usage: $0 [tiny|base|small|all]" >&2; exit 2 ;;
esac

mkdir -p "${WHISPER_ROOT}" "${MODEL_DIR}"

if [[ ! -d "${REPO}/.git" ]]; then
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp "${REPO}"
else
  git -C "${REPO}" pull --ff-only
fi

if command -v cmake >/dev/null 2>&1; then
  CMAKE="$(command -v cmake)"
elif [[ -x /opt/homebrew/bin/cmake ]]; then
  CMAKE="/opt/homebrew/bin/cmake"
elif [[ -x /usr/local/bin/cmake ]]; then
  CMAKE="/usr/local/bin/cmake"
elif command -v brew >/dev/null 2>&1; then
  brew install cmake
  CMAKE="$(command -v cmake)"
else
  TOOLS_DIR="${ROOT}/data/tools"
  CMAKE_VERSION="${LEOJARVIS_CMAKE_VERSION:-4.3.3}"
  CMAKE_DIR="${TOOLS_DIR}/cmake-${CMAKE_VERSION}-macos-universal"
  CMAKE="${CMAKE_DIR}/CMake.app/Contents/bin/cmake"
  if [[ ! -x "${CMAKE}" ]]; then
    mkdir -p "${TOOLS_DIR}"
    curl -L --fail --connect-timeout 15 --max-time 240 \
      -o "${TOOLS_DIR}/cmake-${CMAKE_VERSION}-macos-universal.tar.gz" \
      "https://cmake.org/files/v${CMAKE_VERSION%.*}/cmake-${CMAKE_VERSION}-macos-universal.tar.gz"
    tar -xzf "${TOOLS_DIR}/cmake-${CMAKE_VERSION}-macos-universal.tar.gz" -C "${TOOLS_DIR}"
  fi
fi

"${CMAKE}" -S "${REPO}" -B "${REPO}/build" -DGGML_METAL=ON
"${CMAKE}" --build "${REPO}/build" --config Release -j

download_model() {
  local name="$1"
  if [[ -f "${MODEL_DIR}/ggml-${name}.bin" ]]; then
    echo "Model exists: ${MODEL_DIR}/ggml-${name}.bin"
    return
  fi
  bash "${REPO}/models/download-ggml-model.sh" "${name}" "${MODEL_DIR}"
}

if [[ "${MODEL}" == "all" ]]; then
  download_model tiny
  download_model base
  download_model small
else
  download_model "${MODEL}"
fi

BIN="${REPO}/build/bin/whisper-cli"
[[ -x "${BIN}" ]] || BIN="${REPO}/build/bin/main"
if [[ -x "${BIN}" && "$(uname -s)" == "Darwin" ]]; then
  install_name_tool -add_rpath @executable_path "${BIN}" 2>/dev/null || true
  codesign --force --sign - "${BIN}" >/dev/null 2>&1 || true
fi

echo "whisper binary: ${BIN}"
echo "model dir: ${MODEL_DIR}"
echo "installed models:"
find "${MODEL_DIR}" -maxdepth 1 -name 'ggml-*.bin' -print
