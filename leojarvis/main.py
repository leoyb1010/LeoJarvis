from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api.routes import router
from .config import ROOT, settings
from .scheduler import setup_scheduler

_sched = None
_WEB_DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sched
    db.init_db()
    _warm_caches()
    _sched = setup_scheduler()
    _sched.start()
    yield
    if _sched:
        _sched.shutdown()
    # 退出时关掉本进程拉起的 SSH 隧道，避免孤儿进程占住 local_port，
    # 下次启动撞上「端口在监听但 HTTP 不通」的半死隧道。
    from . import remote_cortex
    remote_cortex.shutdown_all()


def _warm_caches() -> None:
    """后台预热慢探测（AI 工具 / 天气），让首屏驾驶舱直接命中缓存，不卡顿。"""
    import threading

    def _warm() -> None:
        try:
            from .agent import sysinfo
            sysinfo.ai_tool_status(block=True)
            sysinfo.weather()
            # 预热驾驶舱总览缓存，首屏直接命中，避免第一次点击卡 1~2s。
            from .cockpit import overview
            overview(force=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[warmup] failed: {exc}")

    threading.Thread(target=_warm, daemon=True).start()


app = FastAPI(title="LeoJarvis", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
# API 前缀别名：避免将来新增前端路由名与 API 名冲突；旧的无前缀接口继续兼容。
app.include_router(router, prefix="/api")


# ---------- 生产前端：把构建好的静态资源挂到同一进程，单端口稳定上线 ----------
# 开发时用 vite(5173)；上线只跑后端 8787，由它直接吐 web/dist，避免 dev server 挂掉。
if _WEB_DIST.is_dir() and (_WEB_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(_WEB_DIST / "assets")), name="assets")

    def _index_response() -> FileResponse:
        return FileResponse(
            str(_WEB_DIST / "index.html"),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    @app.get("/")
    def _serve_index() -> FileResponse:
        return _index_response()

    @app.get("/{full_path:path}")
    def _spa_fallback(full_path: str) -> FileResponse:
        # 真实存在的静态文件直接返回，其余路径回退到 index.html（前端路由）。
        candidate = _WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return _index_response()


def run() -> None:
    import uvicorn

    cfg = settings().get("server", {})
    uvicorn.run("leojarvis.main:app", host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 8787)), reload=False)


if __name__ == "__main__":
    run()
