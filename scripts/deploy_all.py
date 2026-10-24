"""Golden path: run every stage end to end from a clean checkout.

Usage::

    python -m scripts.deploy_all                  # full run, downloads raw data
    python -m scripts.deploy_all --skip-download  # reuse cached raw data
    python -m scripts.deploy_all --n-trials 1     # bounded teaching run
    python -m scripts.deploy_all --skip-api       # stop before the API check

"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "artifacts" / "deploy_all"

API_HOST = "127.0.0.1"
API_PORT = 8000
API_READY_TIMEOUT_S = 120


@dataclass
class StageResult:
    """Outcome of one stage."""

    name: str
    command: str
    ok: bool
    seconds: float
    log_path: Path | None = None
    detail: str = ""
    produced: list[str] = field(default_factory=list)


def _present(*relative: str) -> list[str]:
    """Return the relative paths that exist, annotated with their size."""
    found = []
    for rel in relative:
        path = REPO_ROOT / rel
        if path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file()]
            if files:
                size = sum(p.stat().st_size for p in files)
                found.append(f"{rel} ({len(files)} files, {size / 1e6:.1f} MB)")
        elif path.is_file():
            found.append(f"{rel} ({path.stat().st_size / 1e6:.1f} MB)")
    return found


def _run_stage(
    name: str,
    module_args: list[str],
    produces: tuple[str, ...],
) -> StageResult:
    """Run one documented module entry point and capture its output."""
    command = f"{Path(sys.executable).name} -m " + " ".join(module_args)
    log_path = LOG_DIR / f"{name.replace(' ', '_').lower()}.log"

    logger.info("--> %s", name)
    logger.info("    %s", command)

    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", *module_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    seconds = time.monotonic() - started

    log_path.write_text(
        f"$ {command}\n\n--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}",
        encoding="utf-8",
    )

    ok = completed.returncode == 0
    detail = "" if ok else f"exit code {completed.returncode}"
    if not ok:
        tail = (completed.stderr or completed.stdout).strip().splitlines()[-3:]
        detail = f"exit code {completed.returncode}: " + " | ".join(tail)

    return StageResult(
        name=name,
        command=command,
        ok=ok,
        seconds=seconds,
        log_path=log_path,
        detail=detail,
        produced=_present(*produces) if ok else [],
    )


def _check_api() -> StageResult:
    """Start the API, poll /health, and require a usable readiness payload."""
    name = "API readiness"
    command = (
        f"{Path(sys.executable).name} -m uvicorn src.serving.api:app "
        f"--host {API_HOST} --port {API_PORT}"
    )
    log_path = LOG_DIR / "api_readiness.log"
    health_url = f"http://{API_HOST}:{API_PORT}/health"

    logger.info("--> %s", name)
    logger.info("    %s", command)

    started = time.monotonic()
    api_log = log_path.open("w", encoding="utf-8")
    api_log.write(f"$ {command}\n\n")
    api_log.flush()

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.serving.api:app",
            "--host",
            API_HOST,
            "--port",
            str(API_PORT),
        ],
        cwd=REPO_ROOT,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )

    payload: dict | None = None
    detail = f"no response from {health_url} within {API_READY_TIMEOUT_S}s"
    try:
        deadline = time.monotonic() + API_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = f"server exited early with code {process.returncode}"
                break
            try:
                with urllib.request.urlopen(health_url, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(1)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        api_log.close()

    seconds = time.monotonic() - started

    ok = False
    if payload is not None:
        # HTTP 200 is not enough: the endpoint can return a degraded payload.
        ok = (
            payload.get("status") == "ok"
            and payload.get("demand_model_loaded") is True
            and payload.get("fare_model_loaded") is True
            and payload.get("history_hours", 0) > 0
            and payload.get("zones", 0) > 0
        )
        detail = json.dumps(payload, separators=(",", ": "))
        if not ok:
            detail = "degraded readiness payload: " + detail

    return StageResult(
        name=name,
        command=command,
        ok=ok,
        seconds=seconds,
        log_path=log_path,
        detail=detail,
    )


def _report(results: list[StageResult], total_seconds: float) -> None:
    """Print the summary table and persist it as JSON."""
    width = max(len(r.name) for r in results)

    print("\n" + "=" * 72)
    print("GOLDEN PATH SUMMARY")
    print("=" * 72)
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"  {status}  {result.name.ljust(width)}  {result.seconds:7.1f}s")
        if result.detail:
            print(f"        {result.detail}")
        for produced in result.produced:
            print(f"        + {produced}")
    print("-" * 72)

    passed = sum(1 for r in results if r.ok)
    print(f"  {passed}/{len(results)} stages passed in {total_seconds:.1f}s total")
    print(f"  Per-stage logs: {LOG_DIR.relative_to(REPO_ROOT)}/")
    print("=" * 72)

    summary_path = LOG_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "completed_at": datetime.now(UTC).isoformat(),
                "python": sys.version.split()[0],
                "total_seconds": round(total_seconds, 1),
                "stages_passed": passed,
                "stages_total": len(results),
                "stages": [
                    {
                        "name": r.name,
                        "command": r.command,
                        "ok": r.ok,
                        "seconds": round(r.seconds, 1),
                        "detail": r.detail,
                        "produced": r.produced,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  Summary: {summary_path.relative_to(REPO_ROOT)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run every project stage end to end from a clean checkout."
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Reuse already-cached raw data instead of downloading.",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=1,
        help="Optuna trials per estimator (default: 1, the bounded teaching run).",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=3,
        help="Hours ahead for the batch forecast (default: 3).",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Stop before starting the API readiness check.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    pipeline_args = ["scripts.run_pipeline"]
    if args.skip_download:
        pipeline_args.append("--skip-download")

    stages: list[tuple[str, list[str], tuple[str, ...]]] = [
        (
            "Data pipeline",
            pipeline_args,
            ("data/raw", "data/processed", "data/features"),
        ),
        (
            "Model training",
            ["scripts.train_models", "--n-trials", str(args.n_trials)],
            ("mlflow.db", "mlruns"),
        ),
        (
            "Responsible AI",
            ["scripts.responsible.run_analysis"],
            ("docs/model_cards", "artifacts/responsible"),
        ),
        (
            "Drift report",
            ["scripts.monitoring.demo_drift_report", "--problem", "all", "--mode", "drift"],
            ("artifacts/drift",),
        ),
        (
            "Batch forecast",
            ["scripts.batch_forecast", "--horizon", str(args.horizon)],
            ("predictions.db",),
        ),
    ]

    results: list[StageResult] = []
    started = time.monotonic()

    for name, module_args, produces in stages:
        result = _run_stage(name, module_args, produces)
        results.append(result)
        if not result.ok:
            logger.error("%s failed; later stages depend on it, stopping.", name)
            break
    else:
        if not args.skip_api:
            results.append(_check_api())

    total_seconds = time.monotonic() - started
    _report(results, total_seconds)

    sys.exit(0 if all(r.ok for r in results) else 1)


if __name__ == "__main__":
    main()
