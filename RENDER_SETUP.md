# Render deployment notes

`render.yaml` prepares a Flask/Gunicorn service and a persistent disk for the IBM SQLite database and ADS case database. The blueprint uses the paid Starter service plan and a 10 GB disk; review current Render pricing before applying it. This repository has not been connected to or deployed on Render, so these steps are preparation only.

## Before deploy

1. Link this repository to the intended Render service and review the Blueprint preview carefully.
2. Add the Firebase production values listed in [AUTHENTICATION.md](AUTHENTICATION.md): `FIREBASE_PROJECT_ID`, `FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`, and `FIREBASE_WEB_APP_ID`.
3. Configure Firebase Admin credentials through a protected Render Secret File. Set `GOOGLE_APPLICATION_CREDENTIALS` to its mounted path. Never commit the service-account key.
4. Keep `AUTH_MODE=firebase`, `FLASK_ENV=production`, the generated `SECRET_KEY`, and secure cookies. Production fails at startup when required Firebase web values are absent.
5. Configure the Firebase authorized domain and set trusted custom claims (`analyst`, `reviewer`, or `administrator`) through a trusted administrative process.
6. Provision `/var/data/ibm_hi_small.sqlite3` on the persistent disk. Do not overwrite an existing deployment database without backing it up and reviewing it.

`render.yaml` sets `CASE_DB_PATH=/var/data/ads_app.sqlite3` and keeps both SQLite databases and uploads on the same persistent disk. The service is configured for one Gunicorn worker process and one instance. Uploaded-dataset jobs run in a bounded in-process worker thread; they are not a durable distributed queue. Do not scale horizontally or claim durable job recovery with SQLite; migrate job state and application/case storage to a shared database and managed queue before doing so. IBM full-dataset scoring remains an explicit offline command and is not run during web startup.

## Local database transfer example

Make a consistent backup copy without modifying the local source database:

```powershell
python -c "import sqlite3; src=sqlite3.connect('data/ibm_hi_small.sqlite3'); dst=sqlite3.connect('data/ibm_hi_small.deploy.sqlite3'); src.backup(dst); dst.close(); src.close()"
```

Use the SSH host and service ID shown by Render for your service. Render documents `scp -s` for copying a file over SFTP:

```powershell
scp -s .\data\ibm_hi_small.deploy.sqlite3 <SERVICE_ID>@ssh.<REGION>.render.com:/var/data/ibm_hi_small.sqlite3
```

## Verify after deployment

- `GET /health` is public for the hosting health check and reports database/model readiness.
- `GET /` should show the ADS landing page.
- `GET /auth/login` should show the Firebase sign-in screen.
- `GET /dashboard` and `/api/ibm/summary` should require an authenticated Firebase session.
- Configure a Firebase user and verify sign-in, session expiry, and sign-out before granting reviewer roles.

Do not claim deployment or external report delivery until those behaviors are verified against the live service. The app creates review-ready local evidence; it does not submit to regulators or law enforcement.
