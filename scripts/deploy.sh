#!/usr/bin/env bash
# LeoJarvis 上线脚本：构建前端 → 由后端单端口(8787)托管 dist → 稳定运行。
# 不再依赖 vite dev server(5173)，避免开发服务器挂掉导致页面打不开。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${LEOJARVIS_PORT:-${CORTEX_PORT:-8787}}"

resolve_python() {
  if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; return; fi
  for p in python3.14 python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$p" >/dev/null 2>&1; then PY="$(command -v "$p")"; return; fi
    if [ -x "$p" ]; then PY="$p"; return; fi
  done
  PY=""
}
resolve_python
if [ -z "${PY:-}" ]; then
  echo "!! 找不到 Python。请安装 Python 3.10+，或确认 .venv/bin/python 存在。" >&2
  exit 1
fi
echo "==> 使用 Python: $PY ($("$PY" --version 2>&1))"

# 解析 npm：非交互 shell 通常不会加载 nvm / homebrew 的 PATH，这里主动找一遍。
resolve_npm() {
  if command -v npm >/dev/null 2>&1; then NPM="$(command -v npm)"; return; fi
  # nvm
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    set +u
    # shellcheck disable=SC1090
    . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
    nvm use default >/dev/null 2>&1 || true
    set -u
    if command -v npm >/dev/null 2>&1; then NPM="$(command -v npm)"; return; fi
    local latest
    latest="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
    [ -n "$latest" ] && export PATH="$latest:$PATH"
  fi
  # homebrew / 常见路径 / volta / fnm
  for p in /opt/homebrew/bin /usr/local/bin "$HOME/.volta/bin" "$HOME/.fnm/aliases/default/bin" "$HOME/Library/pnpm"; do
    [ -x "$p/npm" ] && { export PATH="$p:$PATH"; break; }
  done
  command -v npm >/dev/null 2>&1 && NPM="$(command -v npm)" || NPM=""
}
resolve_npm
if [ -z "${NPM:-}" ]; then
  echo "!! 找不到 npm。请确认已安装 Node.js；若用 nvm，请先 'nvm use' 后重试，或把 node 的 bin 目录加入 PATH。" >&2
  echo "   提示：终端里跑 'which npm' 看路径，然后 export PATH=该目录:\$PATH 再跑本脚本。" >&2
  exit 1
fi
echo "==> 使用 npm: $NPM ($("$NPM" -v 2>/dev/null))"

if [ ! -d web/node_modules ]; then
  echo "==> 安装前端依赖 (web/node_modules，首次部署或全新克隆时需要)"
  "$NPM" --prefix web install
fi

echo "==> [1/3] 构建前端 (web/dist)"
"$NPM" --prefix web run build

echo "==> [2/3] 停掉旧后端进程 (:${PORT})"
if lsof -ti "tcp:${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -ti "tcp:${PORT}" -sTCP:LISTEN | xargs kill 2>/dev/null || true
  sleep 1
fi

echo "==> [3/3] 启动后端单进程 (前端+API 同源 :${PORT})"
mkdir -p data
nohup "$PY" -m leojarvis.main > data/cortex.log 2>&1 &
PID=$!
echo "    pid=${PID}, 日志: data/cortex.log"

# 等待健康检查（curl 加 --max-time，避免端口半占用时无限等待）
for i in $(seq 1 30); do
  if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:${PORT}/health" 2>/dev/null; then
    echo "==> 上线成功：打开 http://127.0.0.1:${PORT} （进程 pid=${PID}，日志 data/cortex.log）"
    exit 0
  fi
  # 后端进程已退出说明启动崩溃，立刻报错并打印日志尾部，不再干等。
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "!! 后端进程已退出（启动失败）。日志尾部：" >&2
    tail -n 30 data/cortex.log >&2 || true
    exit 1
  fi
  sleep 0.5
done

echo "!! 后端 15s 内未就绪。日志尾部：" >&2
tail -n 30 data/cortex.log >&2 || true
exit 1
