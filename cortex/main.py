from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api.routes import router
from .config import settings
from .scheduler import setup_scheduler

_sched = None


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
    """后台预热慢探测（AI 工具 / 天气），让首屏驾驶舱直接命中缓存，不卡顿。"""
    import threading

    def _warm() -> None:
        try:
            from .agent import sysinfo
            sysinfo.ai_tool_status(block=True)
            sysinfo.weather()
        except Exception as exc:  # noqa: BLE001
            print(f"[warmup] failed: {exc}")

    threading.Thread(target=_warm, daemon=True).start()


app = FastAPI(title="Cortex", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


def run() -> None:
    import uvicorn

    cfg = settings().get("server", {})
    uvicorn.run("cortex.main:app", host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 8787)), reload=False)


if __name__ == "__main__":
    run()
