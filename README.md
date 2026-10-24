# Taxi Forecasting

Python application for two NYC taxi prediction tasks:

- **Demand:** pickup count for one pickup zone and hour.
- **Fare:** `fare_amount` for one trip

The repository includes data processing, XGBoost/LightGBM training, MLflow
tracking, FastAPI serving, recursive batch forecasts, Streamlit dashboard, and optional AWS
infrastructure templates. It contains no datasets or trained model bundles.


## Start Locally

For the preinstalled Windows course image, follow the
[AWS account and image-access guide](docs/STUDENT_AWS_IMAGE_ACCESS.md) instead of
recreating the environment with the local-install commands below.

Use Python 3.11. From the repository root on Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

On macOS or Linux, use the corresponding POSIX paths:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pytest
```

Tests use synthetic data and do not require downloads, models or AWS access.
Follow [setup](docs/SETUP.md) to download data, train registered models, and
start the API and dashboard. Do not expect working predictions immediately
after cloning: serving requires both registered models and saved demand history.

## Run Everything From a Clean Clone

`scripts/deploy_all.py` runs every stage in dependency order and prints a
pass/fail line per stage. It calls the same module entry points documented in
[setup](docs/SETUP.md) rather than reimplementing them, so it cannot drift from
the documented procedure. Create the environment as shown above first, then:

```powershell
.\.venv\Scripts\python.exe -m scripts.deploy_all
```

```bash
./.venv/bin/python -m scripts.deploy_all
```

Script supports below arguments

`--skip-download` to reuse the cache. 

Useful flags:
`--n-trials` for Optuna trials per estimator (default 1)
`--horizon` for batch forecast hours (default 3)
 `--skip-api` to stop before the readiness check.


This covers the local route only. It needs no cloud account and creates no
billable resources. Deploying the API to AWS is a separate, credentialed
activity — see [the infrastructure runbook](infra/terraform/README.md) and
[L9](docs/L9_AWS_INFRASTRUCTURE_LAB.md).

## Documentation

- [Request and launch the Windows course image](docs/STUDENT_AWS_IMAGE_ACCESS.md)
- [Deploy the API to AWS with CodeBuild](docs/STUDENT_AWS_DEPLOYMENT_WALKTHROUGH.md)
- [Local setup and commands](docs/SETUP.md)
- [API request examples](docs/API_EXAMPLES.md)
- [System architecture](docs/ARCHITECTURE.md)
- [Data scope and model limitations](docs/DATA_STATEMENT.md)
- [Optional AWS infrastructure](infra/terraform/README.md)
- [Recording companion and learner activity map](docs/RECORDING_COMPANION.md)
- [Recorded architecture walkthrough](docs/PROJECT_ARCHITECTURE.md)
- [Historical business report](docs/BUSINESS_REPORT.md)
- [Cloud cost boundaries](docs/COST_OPTIMIZATION.md)

The companion links all L2-L12 learner labs; L1 uses setup and tests. Videos are
provided separately. Lab files, reviewed diagrams, and the exploration notebook
retain the paths shown in the recordings. The notebook has no saved outputs.
Datasets, trained models, and evidence reports must be generated locally; AWS
activities require your own authorized configuration or the stated local fallback.

## Layout

| Path | Responsibility |
| --- | --- |
| `src/data/`, `src/features/` | Download, clean, aggregate, engineer features, and split by time |
| `src/models/` | Tune, train, evaluate, explain, and register models |
| `src/serving/`, `clients/python/` | API contracts, inference, batch forecasting, and HTTP client |
| `src/monitoring/`, `src/responsible/` | Drift, performance comparisons, SHAP, and subgroup metrics |
| `scripts/` | Technical command entrypoints |
| `dashboard/` | Streamlit views calling the API and reading local reports |
| `tests/` | Offline unit and integration checks |
| `notebooks/`, `docs/` | Data exploration, learner activities, and technical references |
| `docker/`, `infra/terraform/`, `retraining/` | Optional packaging and cloud operation |

## Operational Boundaries

Docker, Terraform and AWS are optional for local operation. The cloud templates
are not connected to any account, remote repository or existing deployment.
They can create billable resources if you explicitly deploy them with credentials.
No GitHub Actions workflows or automatic release hooks are configured here.

Historical evaluation does not establish current production quality. The default
forecast follows the latest stored history, not the current clock. Model errors,
duration estimation, drift and subgroup disparities require review before using
predictions to make operational or financial decisions.