from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api.routes import router
from .auth import api_token, bearer_token, is_authorized, is_static_request, is_trusted_local
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


def _warm_caches() -> None:
    """后台预热慢探测，让首屏驾驶舱直接命中缓存。各探测互不依赖，并行跑（原本串行 10~30s，
    npm 网络调用主导），把冷启动期「占位→实数」的窗口压短。"""
    import threading

    def _safe(fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"[warmup] {getattr(fn, '__name__', fn)} failed: {exc}")

    def _warm() -> None:
        from .agent import sysinfo
        # 三个独立慢探测并行预热
        jobs = [
            lambda: sysinfo.ai_tool_status(block=True),
            sysinfo.weather,
            lambda: sysinfo.structured_status(block=True),
        ]
        threads = [threading.Thread(target=_safe, args=(j,), daemon=True) for j in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # overview 依赖上面几项的缓存，最后再预热（此时多半已命中）。
        def _warm_overview() -> None:
            from .cockpit import overview
            overview(force=True)
        _safe(_warm_overview)

    threading.Thread(target=_warm, daemon=True).start()


app = FastAPI(title="LeoJarvis", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _bearer_token_guard(request: Request, call_next):
    client_host = request.client.host if request.client else None
    if (
        not api_token()
        or request.method == "OPTIONS"
        or is_static_request(request.url.path)
        or is_trusted_local(client_host, request.headers)
    ):
        return await call_next(request)

    supplied = bearer_token(request.headers.get("authorization"))
    if not supplied:
        supplied = request.headers.get("x-leojarvis-token", "").strip()

    if not is_authorized(supplied):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


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

    @app.head("/")
    def _serve_index_head() -> FileResponse:
        return _index_response()

    # 后端路由前缀：命中但未被上面的 API 路由匹配 = 真正的 404，不能回退到 index.html，
    # 否则前端把 HTML 当成 JSON 解析，报“接口返回的不是 JSON”这种误导性错误。
    _BACKEND_PREFIXES = ("api/", "health", "ws/", "assets/")

    _DIST_ROOT = _WEB_DIST.resolve()

    @app.get("/{full_path:path}")
    def _spa_fallback(full_path: str):
        # 真实存在的静态文件直接返回，其余路径回退到 index.html（前端路由）。
        # 解析后必须仍在 dist/ 内，挡掉 `../` 目录穿越读到任意本地文件。
        candidate = (_WEB_DIST / full_path).resolve()
        if candidate.is_file() and _DIST_ROOT in candidate.parents:
            return FileResponse(str(candidate))
        if full_path.startswith(_BACKEND_PREFIXES):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"no such endpoint: /{full_path}")
        return _index_response()


def run() -> None:
    import uvicorn

    cfg = settings().get("server", {})
    uvicorn.run("leojarvis.main:app", host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 8787)), reload=False)


if __name__ == "__main__":
    run()
