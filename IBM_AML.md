# IBM HI-Small investigation platform

The Flask home page is now an IBM HI-Small investigation desk. It uses the existing IBM transaction database and saved SGD model; it does not ingest or train at web startup. The former multi-dataset pages still exist under their legacy routes, but the home dashboard uses only the IBM dataset and IBM evaluation artifact.

## Local Windows setup

### One-time environment setup

```powershell
cd C:\Users\tejas\ADS-Webapp
.\setup_windows.bat
```

The script creates `.venv`, installs `requirements.txt`, and copies `.env.example` to `.env` if needed. The development secret is generated per process; do not set a production secret in a committed file.

### Dataset and database

Set the path to the actual transaction CSV from the matching HI-Small release:

```powershell
$env:IBM_AML_SOURCE = 'C:\path\to\HI-Small_Trans.csv'
.\.venv\Scripts\Activate.ps1
python -m training.ibm_pipeline inspect
```

The full database used in this workspace is `data\ibm_hi_small.sqlite3` (5,078,345 transactions). If it is present, keep it and do not import again. If you are setting up a new machine, run:

```powershell
python -m training.ibm_pipeline ingest
```

A complete import is reused automatically. `--force` rebuilds it and should be used only when deliberately replacing a local import. The transaction CSV is not included in the repository.

### Model training and batch scores

The fitted model and evaluation report are included at:

- `models\ibm_hi_small_sgd.joblib`
- `reports\ibm_hi_small_metrics.json`

Retrain only when intended:

```powershell
python -m training.ibm_pipeline train
python -m training.ibm_pipeline compare-thresholds
```

Scoring all transactions is a separate resumable job. First review the measured preflight; the estimate includes inference throughput and conservative storage planning. On this machine the previous run took several minutes to write all scores, used about 1 GB additional SQLite storage, and left the source labels untouched.

```powershell
python -m training.ibm_pipeline estimate-score
python -m training.ibm_pipeline score --yes --chunk-size 50000
```

The job writes score batches into `transaction_scores` and exposes progress at `/api/ibm/scoring/progress`. Re-running the command skips already-scored transaction/model pairs. Web startup never starts or resumes scoring.

### Run, test, and check readiness

```powershell
.\run_local.bat
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
Invoke-RestMethod http://127.0.0.1:5000/api/ibm/summary
python -m unittest discover -s tests -v
```

`/health` distinguishes service availability from database and model readiness. To run the production-style WSGI server locally, activate `.venv` and use `waitress-serve --listen=127.0.0.1:5000 app:app`.

## Dashboard features

- Overview totals, ground-truth label prevalence, model-scored and model-flagged counts, daily activity, payment formats, currency-separated received totals, risk classes, and saved model metrics.
- Transaction explorer with server-side pagination, transaction/account/bank lookup, date range, currency, format, actual-label, and model-score filters. Results are capped at 200 rows; CSV transaction exports are capped at 100,000.
- Transaction detail modal with separate actual label and prediction, score, threshold, model version, and score timestamp. The local explanation displays additive contributions in the model's hashed feature space; bucket collisions can combine effects, and contributions are not causal explanations.
- Interactive, bounded directed account network. Bank/account pairs remain distinct, expansion is limited to two hops and 300 edges, and currently displayed edges can be exported.
- Deterministic investigation assistant with bounded query functions for transaction IDs, top scores, date counts, account lookup (bank and account required), and saved model metrics. It never executes user-provided SQL.
- Account activity CSV groups totals by bank, account, and currency; incoming and outgoing amounts are kept in separate fields.

## API reference

- `GET /health` — service, transaction database, and model readiness.
- `GET /api/ibm/health` — IBM-specific readiness.
- `GET /api/ibm/summary` — import metadata, transaction/account totals, actual label prevalence, scoring totals/progress, and model report.
- `GET /api/ibm/analytics` — daily activity, payment-format counts, currency-separated received amounts, and scored-class counts.
- `GET /api/ibm/transactions?limit=25&offset=0&q=...&start=2022-09-01&end=2022-09-10&payment_format=Wire&currency=US%20Dollar&label=1&min_risk=0.5` — parameterized search, capped pagination.
- `GET /api/ibm/transactions/<transaction_id>` — source record plus persisted score when available.
- `GET /api/ibm/transactions/<transaction_id>/explanation` — additive linear-model feature contributions.
- `GET /api/ibm/graph?bank=010&account=8000EBD30&depth=1&limit=100` — bounded directed subgraph.
- `GET /api/ibm/export/transactions.csv?...` — filtered transaction export, max 100,000 rows.
- `GET /api/ibm/export/accounts.csv?limit=50000` — currency-separated incoming/outgoing aggregates, max 100,000 rows.
- `GET /api/ibm/export/network.csv?bank=010&account=8000EBD30&depth=1&limit=100` — edge list for the bounded displayed subgraph.
- `GET /api/ibm/scoring/progress` — batch status.
- `GET /api/ibm/assistant?q=...` — deterministic evidence-grounded answers.

## Model and source interpretation

The source transaction schema has 11 expected columns. The repeated account header is parsed as `Account` (sender) and `Account.1` (recipient). Bank and account identifiers are kept as strings, including zero padding. Transaction IDs are stable dataset-prefixed source-row IDs; repeated source rows are not dropped. The supplied HI-Small transaction file had 5,078,345 rows, 5,177 positive labels (0.10194%), no missing cells, and a timestamp range of 2022-09-01 00:00 to 2022-09-18 16:18.

The SGD log-loss model uses hashed log amounts, hour/day, payment/receiving currency, payment format, and same-bank indicator. Raw account IDs, transaction IDs, timestamps, and the target are excluded from features. It was trained on Sep 1–8, threshold-tuned on Sep 9, and evaluated on Sep 10–18: 4,214,445 train, 654,467 validation, and 209,433 test rows. Test average precision was 0.03653, ROC-AUC 0.84426, precision 0.04568, recall 0.76026, F1 0.08619; confusion matrix TN/FP/FN/TP = 190,914/17,422/263/834. The validation-tuned threshold was `3.3523686685124594e-43`. False positives are numerous; model flags are investigation leads, never proof. Test prevalence (0.5238%) is higher than overall source prevalence.

## Render deployment

`render.yaml` sets the existing service name (`ads-ef6q`), Gunicorn startup, `/health`, production secret generation, model/report paths, and a 10 GB persistent disk mounted at `/var/data`. The checked-in model and metrics files are not ignored; the 2.45 GB SQLite database is not checked into Git. The existing Render service must be on a paid plan for a persistent disk, and the disk is attached to only one service instance. Render's default filesystem is ephemeral, while disk-backed deploys have a brief instance swap; see [Render persistent disks](https://render.com/docs/disks), [SSH and shell access](https://render.com/docs/ssh), and [Flask deployment](https://render.com/docs/deploy-flask).

Deployment steps:

1. Push this repository to the branch connected to the existing `ads-ef6q` Render web service. In the Render Blueprint preview, confirm it will update that service and use the paid `starter` plan with the `ibm-aml-data` disk before applying it. The 10 GB disk setting may incur charges; do not apply it on a free service.
2. After the disk is mounted at `/var/data`, create a consistent local backup copy without modifying the working database:

   ```powershell
   python -c "import sqlite3; src=sqlite3.connect('data/ibm_hi_small.sqlite3'); dst=sqlite3.connect('data/ibm_hi_small.deploy.sqlite3'); src.backup(dst); dst.close(); src.close()"
   ```

3. Enable SSH for the paid service and use the service SSH host/ID shown in its Render Connect panel. Copy the deployment backup to the mounted path (Render documents `scp -s` for SFTP):

   ```powershell
   scp -s .\data\ibm_hi_small.deploy.sqlite3 <SERVICE_ID>@ssh.<REGION>.render.com:/var/data/ibm_hi_small.sqlite3
   ```

   Do not overwrite a database already on the Render disk without taking a backup and reviewing it first. This prepared configuration does not perform a live transfer or reset the service database.

4. In Render, confirm `FLASK_ENV=production`, generated `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`, `IBM_AML_DB=/var/data/ibm_hi_small.sqlite3`, and the model/metrics paths from `render.yaml`. Redeploy.
5. Verify `https://<your-service>.onrender.com/health`, `/api/ibm/summary`, and the dashboard. The expected database totals are 5,078,345 transactions and 5,177 actual positives; scoring should show 5,078,345 rows for `hi-small-sgd-v1` when the scored local backup is uploaded.

The app was not connected to Render from this workspace, so no live deployment is claimed. SQLite plus one instance is suitable for this portfolio/demo workload, not horizontal scaling. For multi-instance production use, migrate the IBM tables and score tables to managed PostgreSQL; that migration is not included here.

## Current investigation workflow and remaining work

- Firebase production sign-in and server-verified session cookies are documented in [AUTHENTICATION.md](AUTHENTICATION.md). Firebase project values and Admin credentials must be supplied by the operator; no real project has been configured or live sign-in verified here. The local analyst shortcut is explicitly development-only.
- Review cases can be opened from persisted IBM model-flagged transactions. Notes and status changes are recorded with append-only audit events. Reviewer decisions require a reviewer/admin identity and a reason. `cleared` records a reviewer decision based on available evidence; it is not proof that the activity is legitimate. The queue is currently a bounded recent alert preview, not a background-enqueued case for every score.
- A marked-for-reporting case produces an internal review preview only. There is no external reporting integration, and report delivery is never implied.
- The authenticated upload workflow supports CSV files mapped to the IBM-compatible feature schema. It separates labeled evaluation from unlabeled analysis, validates values while a bounded background thread runs, stores each run under its owner, paginates results, and provides CSV/PDF exports. The configured upload limit is 16 MB. The worker runs in-process and is intended for a single web instance; it is not a durable distributed queue, and an interrupted run needs operator/user retry while its source file remains available.
- Case and analysis-run PDFs are generated from persisted records. They are internal evidence packages and do not submit reports externally.
- More advanced graph analytics (cycles, fan-in/fan-out clustering) and account metadata/pattern-file enrichment.
- Uploaded-analysis alerts are not yet integrated into the human case queue. Dataset-specific ownership and analysis records exist; cross-analysis case association remains outstanding.
- Model candidate benchmarking beyond the saved SGD baseline remains to be completed. No replacement model has been selected.
- Global model feature importance. Local explanations are additive hashed-space terms and may have hash collisions.
