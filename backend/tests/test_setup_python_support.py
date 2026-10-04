"""Static checks of the setup scripts' Python policy: 3.11 recommended and tried first; 3.11-3.14 supported;
an existing backend/.venv is version-checked and rebuilt safely instead of being reused silently.
(The scripts themselves were exercised end to end in the build environment; see docs/RUN_LOCAL.md.)"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS = (ROOT / "setup.ps1").read_text(encoding="utf-8")
SH = (ROOT / "setup.sh").read_text(encoding="utf-8")
SUPPORTED = ["3.11", "3.12", "3.13", "3.14"]


def test_powershell_supported_versions_in_preference_order():
    m = re.search(r"\$SupportedPython = @\(([^)]*)\)", PS)
    assert m and re.findall(r"'(3\.\d+)'", m.group(1)) == SUPPORTED


def test_bash_supported_versions_in_preference_order():
    assert 'SUPPORTED="3.11 3.12 3.13 3.14"' in SH
    assert "for c in python3.11 python3.12 python3.13 python3.14 python3; do" in SH


def test_existing_venv_is_checked_and_rebuilt_safely():
    for text, keep in ((PS, "-KeepVenv"), (SH, "--keep-venv")):
        assert "backend" in text and "will be rebuilt" in text and keep in text
        assert "venv-previous" in text and "restored unchanged" in text


def test_competition_runtime_unchanged():
    assert "FROM python:3.11-slim" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'target-version = "py311"' in (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
