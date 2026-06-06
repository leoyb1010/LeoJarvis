#!/usr/bin/env bash
# LeoJarvis 上线脚本：构建前端 → 由后端单端口(8787)托管 dist → 稳定运行。
# 不再依赖 vite dev server(5173)，避免开发服务器挂掉导致页面打不开。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${CORTEX_PORT:-8787}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "==> [1/3] 构建前端 (web/dist)"
npm --prefix web run build

echo "==> [2/3] 停掉旧后端进程 (:$PORT)"
if lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -ti "tcp:$PORT" -sTCP:LISTEN | xargs kill 2>/dev/null || true
  sleep 1
fi

echo "==> [3/3] 启动后端单进程 (前端+API 同源 :$PORT)"
mkdir -p data
nohup "$PY" -m leojarvis.main > data/cortex.log 2>&1 &
PID=$!
echo "    pid=$PID, 日志: data/cortex.log"

# 等待健康检查
for i in $(seq 1 20); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null; then
    echo "==> 上线成功：打开 http://127.0.0.1:$PORT"
    exit 0
  fi
  sleep 0.5
done

echo "!! 后端未在 10s 内就绪，请查看 data/cortex.log" >&2
exit 1
