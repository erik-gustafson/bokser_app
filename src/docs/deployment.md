# Synology Git Remote Deployment

This repository supports two environments:

- Local `dev` with `docker/docker-compose.yml` and `docker/docker-compose.dev.yml`
- NAS `prod` with `docker/docker-compose.yml`

Production deploys are driven by a bare Git repo on the NAS. Its `post-receive`
hook checks out the pushed commit into `APP_DIR`, runs Compose, health-checks
the API, and rolls back on failure.

## Files

- `scripts/git-deploy-prod`
- `scripts/bootstrap_nas.sh`
- `scripts/install_git_aliases.sh`
- `nas-hooks/post-receive.production`
- `alembic.ini`
- `docker/.env`
- `docker/docker-compose.yml`
- `docker/docker-compose.dev.yml`
- `docker/Dockerfile`
- `docker/requirements.txt`

## 1) Configure Git Remotes Locally

From this repo:

```bash
git remote add origin <your-origin-url>
git remote add production bokser_admin@bokser_home_nas:~/git/bokser_app-production.git
```

## 2) Branch Workflow

Do day-to-day work on `dev`. Treat `main` as deploy-only.

Recommended flow:

```bash
git checkout dev
git add ...
git commit -m "describe change"
git push
git deploy-prod
```

Notes:

- `git push` is enough on `dev` if the branch already tracks `origin/dev`.
- `git push origin dev` is only needed the first time, or if upstream tracking is not set.
- Avoid developing directly on `main`. `git deploy-prod` promotes `origin/dev` to `origin/main`; it does not commit local changes for you.

## 3) Bootstrap the Production Bare Repo + Hook on NAS

Copy this repo to the NAS, or run from a checked-out copy on the NAS, then:

```bash
bash scripts/bootstrap_nas.sh
```

This initializes:

- `~/git/bokser_app-production.git`

and installs:

- `nas-hooks/post-receive.production` -> `~/git/bokser_app-production.git/hooks/post-receive`

If you change the hook template later, reinstall it with:

```bash
install -m 755 nas-hooks/post-receive.production ~/git/bokser_app-production.git/hooks/post-receive
```

## 4) Configure Production Hook Variables

Edit `nas-hooks/post-receive.production` as needed for your NAS layout.

Defaults in this repo:

- `APP_DIR=/volume1/docker/bokser_app`
- `ENV_FILE=docker/.env`
- `BASE_COMPOSE=docker/docker-compose.yml`
- `HEALTH_URL=http://127.0.0.1:8010/health/status`
- `LOG_SERVICES=("bokser_app_api" "bokser_app_worker")`

Production `docker/.env` should align with:

- `LAKE_ROOT=/app/data_lake`
- `LOGS_ROOT=/app/logs`
- `DOWNLOADS_ROOT=/app/downloads`
- `REPORTING_ARCHIVE_ROOT=/app/reporting_archive`
- `LAKE_HOST_PATH=/volume1/docker/bokser_app/data_lake`
- `LOGS_HOST_PATH=/volume1/docker/bokser_app/logs`
- `DOWNLOADS_HOST_PATH=/volume1/docker/downloads`
- `REPORTING_ARCHIVE_HOST_PATH=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive`

Ensure `docker/.env` is populated for SOS OAuth:

- `SOS_TOKEN_URL`
- `SOS_CLIENT_ID`
- `SOS_CLIENT_SECRET`
- `SOS_OAUTH_REDIRECT_URI`
- `SOS_REFRESH_TOKEN` if used in production
- `SOS_AUTHORIZATION_CODE` only if you still rely on the fallback exchange path

Keep using `--env-file docker/.env` in Compose commands. Compose uses that file
to resolve image names, ports, and bind mount paths, and `env_file: .env`
passes runtime variables into the containers.

## 5) Prepare Runtime Directories

Create production NAS directories:

```bash
mkdir -p /volume1/docker/bokser_app/data_lake
mkdir -p /volume1/docker/bokser_app/logs
mkdir -p /volume1/docker/downloads
mkdir -p /volume1/Bokser_Home/Operations/Reports/Reporting_Archive
```

Make the production bind-mount directories writable by the container runtime
user. If `chown` is allowed on your NAS, prefer that:

```bash
chown -R 1000:1000 /volume1/docker/bokser_app/data_lake
chown -R 1000:1000 /volume1/docker/bokser_app/logs
chown -R 1000:1000 /volume1/docker/downloads
```

If Synology ownership changes are blocked, use a permissive fallback:

```bash
chmod -R 777 /volume1/docker/bokser_app/data_lake
chmod -R 777 /volume1/docker/bokser_app/logs
chmod -R 777 /volume1/docker/downloads
```

For local development on Windows, create:

```powershell
New-Item -ItemType Directory -Force C:\Users\erik\Code\data_lake\dev
New-Item -ItemType Directory -Force C:\Users\erik\Code\bokser_app\logs
New-Item -ItemType Directory -Force C:\Users\erik\Code\test_downloads
```

For local reporting archive access, ensure
`Z:\Operations\Reports\Reporting_Archive` is mounted before starting the dev
Compose stack.

## 6) Example `.env` Values

Example production `docker/.env` values:

```env
COMPOSE_PROJECT_NAME=bokser_app_prod
MIGRATE_CONTAINER_NAME=bokser_app_migrate_prod
API_CONTAINER_NAME=bokser_app_api_prod
WORKER_CONTAINER_NAME=bokser_app_worker_prod
APP_IMAGE=bokser_app_prod:latest
APP_ENV=prod
API_HOST_PORT=8010
LAKE_HOST_PATH=/volume1/docker/bokser_app/data_lake
LOGS_HOST_PATH=/volume1/docker/bokser_app/logs
DOWNLOADS_HOST_PATH=/volume1/docker/downloads
REPORTING_ARCHIVE_HOST_PATH=/volume1/Bokser_Home/Operations/Reports/Reporting_Archive
DB_NET_NAME=db_net
DB_NET_EXTERNAL=true
```

To update an existing NAS production checkout that still points at the old lake
path:

```bash
cd /volume1/docker/bokser_app
sed -i 's#^LAKE_HOST_PATH=.*#LAKE_HOST_PATH=/volume1/docker/bokser_app/data_lake#' docker/.env
mkdir -p /volume1/docker/bokser_app/data_lake
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

## 7) Run With Docker Compose

Local Windows checkout at `C:\Users\erik\Code\bokser_app`:

```powershell
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d --build
```

NAS production checkout at `/volume1/docker/bokser_app`:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

The Compose projects are intentionally separated as `bokser_app_dev` and
`bokser_app_prod` so local dev and NAS production do not share Compose state.

## 8) Database Migrations

Create a revision from model metadata in local dev:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml run --rm --no-deps migrate alembic -c /app/alembic.ini revision --autogenerate -m "describe change"
```

Apply migrations in local dev:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml run --rm --no-deps migrate alembic -c /app/alembic.ini upgrade head
```

Apply migrations on the NAS with only the base Compose file:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml run --rm --no-deps migrate alembic -c /app/alembic.ini upgrade head
```

## 9) Deploy Commands

Production:

```bash
bash scripts/git-deploy-prod
```

Optional alias:

```bash
bash scripts/install_git_aliases.sh
git deploy-prod
```

## Notes

- Hooks support either `/usr/local/bin/docker-compose` or `docker compose`.
- The production hook exits non-zero if the new revision fails health checks after rollback is attempted.
- `scripts/git-deploy-prod` only promotes `origin/dev` to `origin/main` if fast-forward is possible.
- The Docker services build from `docker/Dockerfile`.
