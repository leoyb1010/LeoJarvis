#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request


BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8787"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 6

CHECKS = [
    ("health", "/health", 500),
    ("cockpit", "/api/cockpit/overview", 1800),
    ("briefing_compact", "/api/briefing/today?compact=1&limit=24", 2200),
    ("notes_compact", "/api/personal-notes?compact=1", 900),
    ("notebooks", "/api/personal-notes/notebooks", 900),
    ("devices", "/api/devices", 1800),
    ("device_ops_cached", "/api/device-ops/status", 2200),
]


def fetch(path: str) -> tuple[int, float, int]:
    started = time.perf_counter()
    with urllib.request.urlopen(BASE + path, timeout=8) as response:
        raw = response.read()
        status = response.status
    elapsed = (time.perf_counter() - started) * 1000
    if raw:
        json.loads(raw.decode("utf-8"))
    return status, elapsed, len(raw)


def p95(values: list[float]) -> float:
    if len(values) < 2:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def main() -> int:
    failures: list[str] = []
    print(f"LeoJarvis perf smoke: base={BASE} rounds={ROUNDS}")
    for name, path, threshold_ms in CHECKS:
        values: list[float] = []
        size = 0
        status = 0
        for _ in range(ROUNDS):
            status, elapsed, size = fetch(path)
            values.append(elapsed)
        avg = statistics.mean(values)
        worst = max(values)
        tail = p95(values)
        print(
            f"{name:18s} status={status} avg={avg:7.1f}ms "
            f"p95={tail:7.1f}ms max={worst:7.1f}ms bytes={size} threshold={threshold_ms}ms"
        )
        if status >= 400:
            failures.append(f"{name}: http {status}")
        if tail > threshold_ms:
            failures.append(f"{name}: p95 {tail:.1f}ms > {threshold_ms}ms")
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
