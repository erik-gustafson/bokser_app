# Synology Git Remote Deployment

This repository includes a deploy flow matching your existing model:

- Push to `staging` bare repo `dev` branch -> staging deploy.
- Push to `production` bare repo `main` branch -> production deploy.
- NAS `post-receive` hook checks out the pushed commit into `APP_DIR`, runs Compose, health-checks, and rolls back on failure.

## Files Added

- `scripts/git-deploy-staging`
- `scripts/git-deploy-prod`
- `scripts/bootstrap_nas.sh`
- `scripts/install_git_aliases.sh`
- `nas-hooks/post-receive.staging`
- `nas-hooks/post-receive.production`
- `alembic.ini`
- `src/database/Alembic/`
- `docker/.env`
- `docker/docker-compose.yml`
- `docker/docker-compose.dev.yml`
- `docker/worker.Dockerfile`
- `docker/requirements.txt`

## 1) Configure Git Remotes Locally

From this repo:

```bash
git remote add origin <your-origin-url>
git remote add staging bokser_admin@bokser_home_nas:~/git/bokser_app-staging.git
git remote add production bokser_admin@bokser_home_nas:~/git/bokser_app-production.git
```

## 2) Bootstrap Bare Repos + Hooks on NAS

Copy this repo to NAS (or run from a checked-out copy on NAS), then:

```bash
bash scripts/bootstrap_nas.sh
```

This initializes:

- `~/git/bokser_app-staging.git`
- `~/git/bokser_app-production.git`

and installs hook templates into each bare repo.

## 3) Configure Hook Variables

Edit each hook file as needed:

- `nas-hooks/post-receive.staging`
- `nas-hooks/post-receive.production`

Set these values for your NAS layout:

- `APP_DIR`
  - staging default in this repo: `/volume1/Bokser_Home/Code/bokser_app`
  - production default in this repo: `/volume1/docker/bokser_app`
- `ENV_FILE`
  - default in this repo: `docker/.env`
- `BASE_COMPOSE`
  - default in this repo: `docker/docker-compose.yml`
- `HEALTH_URL`
  - staging default in this repo: `http://127.0.0.1:8011/health/status`
  - production default in this repo: `http://127.0.0.1:8010/health/status`
- `LOG_SERVICES` (Compose service names)
  - `bokser_app_api`
  - `bokser_app_worker`
- `LAKE_ROOT` / `LAKE_HOST_PATH` (in `docker/.env`)
  - `LAKE_ROOT=/data_lake`
  - `DATABASE_URL=sqlite:////data_lake/bokser_app.db`
  - staging `LAKE_HOST_PATH=/volume1/data_lake/staging`
  - production `LAKE_HOST_PATH=/volume1/data_lake/prod`
- Runtime folders mounted into the worker:
  - `LOGS_ROOT=/app/logs`
  - dev downloads default: `C:/Users/erik/Code/test_downloads` -> `/app/test_downloads`
  - staging downloads default: `/volume1/Bokser_Home/Code/downloads`
  - production downloads default: `/volume1/docker/downloads`
  - reporting archive default: `/volume1/Bokser_Home/Operations/Reports/Reporting_Archive`

Then reinstall hooks if you changed templates:

```bash
install -m 755 nas-hooks/post-receive.staging ~/git/bokser_app-staging.git/hooks/post-receive
install -m 755 nas-hooks/post-receive.production ~/git/bokser_app-production.git/hooks/post-receive
```

## 4) Prepare App Directories on NAS

Ensure each `APP_DIR` exists and contains:

- `docker/.env`
- `docker/docker-compose.yml`

`docker/docker-compose.dev.yml` is only for local development. NAS staging and
production run the base Compose file with different `docker/.env` values in
each checkout.

Ensure `docker/.env` is populated for SOS OAuth:

- `SOS_TOKEN_URL`
- `SOS_CLIENT_ID`
- `SOS_CLIENT_SECRET`
- `SOS_OAUTH_REDIRECT_URI`
- `SOS_REFRESH_TOKEN` (preferred runtime path)
- `SOS_AUTHORIZATION_CODE` (fallback exchange path)

Runtime environment values are passed into containers with `env_file: .env`
from `docker/docker-compose.yml`. Keep host-specific values in each checkout's
`docker/.env`; keep code defaults in `src/core/config.py` only when they are
safe defaults and not deployment-specific.

Keep using `--env-file docker/.env` in Compose commands. That file is used once
by Compose to resolve image names, ports, and bind mount paths, and again by
`env_file: .env` to pass runtime variables into the containers.

Create data lake directories:

```bash
mkdir -p /volume1/data_lake/staging
mkdir -p /volume1/data_lake/prod
```

Create staging app runtime directories:

```bash
mkdir -p /volume1/Bokser_Home/Code/bokser_app/logs
mkdir -p /volume1/Bokser_Home/Code/downloads
mkdir -p /volume1/Bokser_Home/Operations/Reports/Reporting_Archive
```

Create production app runtime directories:

```bash
mkdir -p /volume1/docker/bokser_app/logs
mkdir -p /volume1/docker/downloads
mkdir -p /volume1/Bokser_Home/Operations/Reports/Reporting_Archive
```

For local development on Windows, create:

```powershell
New-Item -ItemType Directory -Force C:\Users\erik\Code\data_lake\dev
New-Item -ItemType Directory -Force C:\Users\erik\Code\bokser_app\logs
New-Item -ItemType Directory -Force C:\Users\erik\Code\test_downloads
```

For local reporting archive access, ensure `Z:\Operations\Reports\Reporting_Archive`
is mounted before starting the dev Compose stack.

Example staging `docker/.env` values:

```env
COMPOSE_PROJECT_NAME=bokser_app_staging
MIGRATE_CONTAINER_NAME=bokser_app_migrate_staging
API_CONTAINER_NAME=bokser_app_api_staging
WORKER_CONTAINER_NAME=bokser_app_worker_staging
API_IMAGE=bokser_app_api_staging:latest
WORKER_IMAGE=bokser_app_worker_staging:latest
APP_ENV=staging
API_HOST_PORT=8011
LAKE_HOST_PATH=/volume1/data_lake/staging
LOGS_HOST_PATH=/volume1/Bokser_Home/Code/bokser_app/logs
DOWNLOADS_ROOT=/volume1/Bokser_Home/Code/downloads
NAS_DOWNLOAD_PATH=/volume1/Bokser_Home/Code/downloads
DOWNLOADS_HOST_PATH=/volume1/Bokser_Home/Code/downloads
REPORTING_ARCHIVE_ROOT=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
NAS_REPORT_ARCHIVE=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
REPORTING_ARCHIVE_HOST_PATH=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
DB_NET_NAME=db_net
```

Example production `docker/.env` values:

```env
COMPOSE_PROJECT_NAME=bokser_app_prod
MIGRATE_CONTAINER_NAME=bokser_app_migrate_prod
API_CONTAINER_NAME=bokser_app_api_prod
WORKER_CONTAINER_NAME=bokser_app_worker_prod
API_IMAGE=bokser_app_api_prod:latest
WORKER_IMAGE=bokser_app_worker_prod:latest
APP_ENV=prod
API_HOST_PORT=8010
LAKE_HOST_PATH=/volume1/data_lake/prod
LOGS_HOST_PATH=/volume1/docker/bokser_app/logs
DOWNLOADS_ROOT=/volume1/docker/downloads
NAS_DOWNLOAD_PATH=/volume1/docker/downloads
DOWNLOADS_HOST_PATH=/volume1/docker/downloads
REPORTING_ARCHIVE_ROOT=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
NAS_REPORT_ARCHIVE=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
REPORTING_ARCHIVE_HOST_PATH=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
DB_NET_NAME=db_net
```

## 5) Run With Docker Compose

Local Windows checkout at `C:\Users\erik\Code\bokser_app`:

```powershell
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d --build
```

NAS staging checkout at `/volume1/Bokser_Home/Code/bokser_app`:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

NAS production checkout at `/volume1/docker/bokser_app`:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

The Compose projects are intentionally separated as `bokser_app_dev`,
`bokser_app_staging`, and `bokser_app_prod` so staging and production can run
on the same NAS without sharing Compose state.

## 6) Database Migrations

Create a revision from model metadata:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml run --rm --no-deps migrate alembic -c /app/alembic.ini revision --autogenerate -m "describe change"
```

Apply migrations:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml run --rm --no-deps migrate alembic -c /app/alembic.ini upgrade head
```

On the NAS, omit `docker-compose.dev.yml` and run the same command with only
`docker/docker-compose.yml`.

## 7) Deploy Commands

Staging:

```bash
bash scripts/git-deploy-staging
```

Production:

```bash
bash scripts/git-deploy-prod
```

Optional aliases:

```bash
bash scripts/install_git_aliases.sh
git deploy-staging
git deploy-prod
```

## Notes

- Hooks support either `/usr/local/bin/docker-compose` or `docker compose`.
- Hook exits with non-zero status if new revision fails health checks (after attempted rollback).
- The production push script only promotes `origin/dev` to `origin/main` if fast-forward is possible.
- Worker now builds from `docker/worker.Dockerfile` (no runtime `pip install` in container startup).
