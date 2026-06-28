from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_validate_project():
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_project.py"
    spec = importlib.util.spec_from_file_location("validate_project", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_project_skips_runtime_data_dir(tmp_path):
    validator = _load_validate_project()
    (tmp_path / "data" / "whisper").mkdir(parents=True)
    (tmp_path / "data" / "whisper" / "third_party.py").write_text("# " + "TO" + "DO upstream marker\n", encoding="utf-8")
    (tmp_path / "leojarvis").mkdir()
    app_file = tmp_path / "leojarvis" / "main.py"
    app_file.write_text("print('ok')\n", encoding="utf-8")

    files = {Path(p).relative_to(tmp_path).as_posix() for p in validator.find_files(tmp_path)}

    assert "leojarvis/main.py" in files
    assert "data/whisper/third_party.py" not in files
