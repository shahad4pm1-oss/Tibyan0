"""Record the CURRENT test results (backend pytest + frontend browser E2E) into eval/results/test_suite.json.

Runs pytest itself; reads the Playwright JSON report written by `npx playwright test` (frontend/e2e-results.json),
so run the browser suite first. Nothing is estimated: missing reports are recorded as missing.
usage: backend/.venv/bin/python eval/collect_test_suite.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pytest_counts() -> dict:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT / "backend",
                       capture_output=True, text=True, check=False)
    last = [ln for ln in r.stdout.splitlines() if " in " in ln and ("passed" in ln or "failed" in ln)][-1]
    c = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", last)}
    return {"passed": c.get("passed", 0), "failed": c.get("failed", 0) + c.get("error", 0) + c.get("errors", 0),
            "skipped": c.get("skipped", 0), "summary": last.strip("= ")}


def playwright_counts() -> dict | None:
    p = ROOT / "frontend/e2e-results.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text(encoding="utf-8"))["stats"]
    return {"passed": s.get("expected", 0), "failed": s.get("unexpected", 0) + s.get("flaky", 0),
            "skipped": s.get("skipped", 0), "started_at": s.get("startTime"),
            "projects": ["desktop 1280x900", "tablet 820x1180", "mobile 390x844"]}


def main() -> int:
    suites = {"backend_pytest": pytest_counts()}
    pw = playwright_counts()
    if pw:
        suites["browser_e2e_playwright"] = pw
    out = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "suites": suites}
    (ROOT / "eval/results/test_suite.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if all(v["failed"] == 0 for v in suites.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
