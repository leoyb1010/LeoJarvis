from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR

ALLOWED_MODELS = ("tiny", "base", "small")
DEFAULT_MODEL = "base"


def _root() -> Path:
    return Path(os.environ.get("LEOJARVIS_WHISPER_DIR") or (DATA_DIR / "whisper"))


def _repo_dir() -> Path:
    return Path(os.environ.get("LEOJARVIS_WHISPER_CPP_DIR") or (_root() / "whisper.cpp"))


def _model_dir() -> Path:
    return Path(os.environ.get("LEOJARVIS_WHISPER_MODEL_DIR") or (_root() / "models"))


def _binary() -> Path | None:
    explicit = os.environ.get("WHISPER_CPP_BIN") or os.environ.get("LEOJARVIS_WHISPER_BIN")
    candidates = [
        Path(explicit).expanduser() if explicit else None,
        _repo_dir() / "build" / "bin" / "whisper-cli",
        _repo_dir() / "build" / "bin" / "main",
        _repo_dir() / "main",
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("whisper-cli")
    return Path(found) if found else None


def _model_name(value: str | None) -> str:
    model = (value or DEFAULT_MODEL).strip().lower()
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL
    return model


def _model_path(model: str) -> Path:
    return _model_dir() / f"ggml-{_model_name(model)}.bin"


def status() -> dict[str, Any]:
    binary = _binary()
    models = {
        name: {
            "path": str(_model_path(name)),
            "available": _model_path(name).exists(),
            "size_mb": round(_model_path(name).stat().st_size / 1024 / 1024, 1) if _model_path(name).exists() else None,
        }
        for name in ALLOWED_MODELS
    }
    return {
        "ok": True,
        "available": bool(binary) and models[DEFAULT_MODEL]["available"],
        "binary": str(binary) if binary else "",
        "root": str(_root()),
        "model_dir": str(_model_dir()),
        "default_model": DEFAULT_MODEL,
        "allowed_models": list(ALLOWED_MODELS),
        "models": models,
    }


def _decode_audio(data_base64: str) -> bytes:
    value = (data_base64 or "").strip()
    if "," in value and value.split(",", 1)[0].startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value, validate=False)


def _extension(mime_type: str, file_name: str) -> str:
    suffix = Path(file_name or "").suffix.lower().lstrip(".")
    if suffix:
        return suffix
    mime = (mime_type or "").lower()
    if "wav" in mime or "wave" in mime:
        return "wav"
    return "wav"


def _clean_output(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith(("whisper_", "ggml_", "main:", "system_info:", "sampling:")):
            continue
        raw = re.sub(r"^\[[0-9:.,\s>\-]+]\s*", "", raw).strip()
        if raw:
            lines.append(raw)
    return "\n".join(lines).strip()


def transcribe_base64(
    *,
    data_base64: str,
    mime_type: str = "audio/wav",
    file_name: str = "recording.wav",
    model: str = DEFAULT_MODEL,
    language: str = "auto",
    prompt: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    binary = _binary()
    if not binary:
        raise RuntimeError("whisper.cpp binary not installed. Run scripts/install_whisper_cpp.sh first.")
    model_name = _model_name(model)
    model_path = _model_path(model_name)
    if not model_path.exists():
        raise RuntimeError(f"Whisper model '{model_name}' is not installed. Run scripts/install_whisper_cpp.sh {model_name}.")
    audio = _decode_audio(data_base64)
    if not audio:
        raise ValueError("audio is empty")
    ext = _extension(mime_type, file_name)
    if ext != "wav":
        raise ValueError("Only WAV audio is accepted by this endpoint. Web/iOS clients should send 16kHz mono WAV.")

    started = time.time()
    with tempfile.TemporaryDirectory(prefix="leojarvis-stt-") as tmp:
        audio_path = Path(tmp) / f"input.{ext}"
        out_prefix = Path(tmp) / "transcript"
        audio_path.write_bytes(audio)
        cmd = [
            str(binary),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-nt",
            "-otxt",
            "-of", str(out_prefix),
        ]
        lang = (language or "auto").strip().lower()
        if lang and lang != "auto":
            cmd.extend(["-l", lang])
        if prompt.strip():
            cmd.extend(["--prompt", prompt.strip()[:240]])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        transcript_file = out_prefix.with_suffix(".txt")
        text = _clean_output(transcript_file.read_text(encoding="utf-8", errors="ignore")) if transcript_file.exists() else ""
        if not text:
            text = _clean_output(proc.stdout)
        if proc.returncode != 0 and not text:
            raise RuntimeError((proc.stderr or proc.stdout or "whisper.cpp failed").strip()[:800])
        return {
            "ok": True,
            "text": text.strip(),
            "model": model_name,
            "language": lang or "auto",
            "duration_ms": int((time.time() - started) * 1000),
            "binary": str(binary),
        }
