# `scripts/deploy_all.py` — Golden Path Runner

Runs every project stage end to end from a clean checkout, in dependency order,
and prints a PASS/FAIL line per stage.


---

## What it runs

| #   | Stage          | Command it invokes                                                          | Expected outputs                              |
| --- | -------------- | --------------------------------------------------------------------------- | --------------------------------------------- |
| 1   | Data pipeline  | `python -m scripts.run_pipeline [--skip-download]`                          | `data/raw`, `data/processed`, `data/features` |
| 2   | Model training | `python -m scripts.train_models --n-trials N`                               | `mlflow.db`, `mlruns/`                        |
| 3   | Responsible AI | `python -m scripts.responsible.run_analysis`                                | `docs/model_cards`, `artifacts/responsible`   |
| 4   | Drift report   | `python -m scripts.monitoring.demo_drift_report --problem all --mode drift` | `artifacts/drift`                             |
| 5   | Batch forecast | `python -m scripts.batch_forecast --horizon H`                              | `predictions.db`                              |
| 6   | API readiness  | `python -m uvicorn src.serving.api:app --host 127.0.0.1 --port 8000`        | — (health check only)                         |

Stages run sequentially. **If a stage fails, the run stops there** — every later
stage depends on it. Stage 6 is skipped entirely if any earlier stage failed.

---

## Prerequisites

Python 3.11, with the virtualenv created and dependencies installed from the
repository root:

```bash
# macOS / Linux
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```


---

## Running it

Always invoke it as a **module** (`-m scripts.deploy_all`), not as a file path —
it needs the repository root on `sys.path` to import `src.*`. Run from the
repository root.

```bash
# macOS / Linux
./.venv/bin/python -m scripts.deploy_all
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m scripts.deploy_all
```

### Common invocations

```bash
# First run from a clean clone — downloads data, fastest possible tuning
./.venv/bin/python -m scripts.deploy_all

# Re-run after the data is already cached in data/raw
./.venv/bin/python -m scripts.deploy_all --skip-download

# Deeper hyperparameter search (much slower)
./.venv/bin/python -m scripts.deploy_all --skip-download --n-trials 25

# Everything except the API health check (e.g. port 8000 is in use)
./.venv/bin/python -m scripts.deploy_all --skip-download --skip-api

# Longer batch forecast horizon
./.venv/bin/python -m scripts.deploy_all --skip-download --horizon 12
```

---

## Flags

| Flag              | Default | Effect                                                                                                                                                                                                                                                           |
| ----------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--skip-download` | off     | Reuse cached raw data in `data/raw` instead of re-downloading. Requires `data/raw/yellow_tripdata_<year>-<month>.parquet` and `data/raw/taxi_zone_lookup.csv` to already exist (year/month come from `config/config.yaml` → `data.tlc_year` / `data.tlc_month`). |
| `--n-trials N`    | `1`     | Optuna trials per estimator. The default of 1 is the bounded teaching run. Note this **overrides** `config/config.yaml` → `models.n_trials` (25), so a default `deploy_all` run tunes far less than a bare `scripts.train_models` run.                           |
| `--horizon H`     | `3`     | Hours ahead for the batch demand forecast. Also narrower than the config default (`serving.batch_horizon_hours: 24`).                                                                                                                                            |
| `--skip-api`      | off     | Stop after stage 5; do not start uvicorn or poll `/health`.                                                                                                                                                                                                      |

---

## Output

### Console summary

```
========================================================================
GOLDEN PATH SUMMARY
========================================================================
  PASS  Data pipeline     123.4s
        + data/raw (2 files, 50.0 MB)
        + data/processed (3 files, 41.2 MB)
  PASS  Model training     88.1s
  ...
------------------------------------------------------------------------
  6/6 stages passed in 412.7s total
  Per-stage logs: artifacts/deploy_all/
  Summary: artifacts/deploy_all/summary.json
========================================================================
```

Each PASS line is followed by the artifacts that stage produced, with file
counts and sizes. Each FAIL line is followed by the exit code and the last three
lines of stderr.

### Files written

- `artifacts/deploy_all/<stage_name>.log` — full stdout and stderr per stage
  (e.g. `data_pipeline.log`, `model_training.log`, `api_readiness.log`).
- `artifacts/deploy_all/summary.json` — machine-readable summary: timestamp,
  Python version, total seconds, pass count, and per-stage command / ok /
  duration / detail / produced-artifact list.

### Exit code

`0` only if **every** stage passed. `1` otherwise — safe to use as a CI gate.

---

## The API readiness check

Stage 6 does more than check for HTTP 200. It starts uvicorn in a subprocess,
polls `http://127.0.0.1:8000/health` for up to 120 seconds, then requires the
payload to show a genuinely usable server:

- `status == "ok"`
- `demand_model_loaded == true`
- `fare_model_loaded == true`
- `history_hours > 0`
- `zones > 0`

A 200 response with any of these missing is reported as
`degraded readiness payload: {...}` and the stage **fails**. The server is
always terminated afterwards (SIGTERM, then SIGKILL after 10s), so no uvicorn
process is left running.

---


## Notes

- This covers the local route only. It creates no billable cloud resources and
  needs no AWS account. Deploying the API to AWS is separate — see the
  [infrastructure runbook](../infra/terraform/README.md).
- Re-running is safe and idempotent in effect: stages overwrite their outputs.
  MLflow runs accumulate in `mlflow.db` / `mlruns/` rather than being replaced.
- Historical evaluation does not establish current production quality. Review
  model errors, drift and subgroup disparities before acting on any prediction.
