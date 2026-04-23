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
- `docker/.env`
- `docker/docker-compose.yml`
- `docker/docker-compose.staging.yml`
- `docker/docker-compose.prod.yml`
- `docker/worker.Dockerfile`
- `docker/requirements.worker.txt`

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
- `BASE_COMPOSE` and `ENV_COMPOSE`
  - staging defaults in this repo:
    - `docker/docker-compose.yml`
    - `docker/docker-compose.staging.yml`
  - production defaults in this repo:
    - `docker/docker-compose.yml`
    - `docker/docker-compose.prod.yml`
- `HEALTH_URL`
  - staging default in this repo: `http://127.0.0.1:8011/health/status`
  - production default in this repo: `http://127.0.0.1:8010/health/status`
- `LOG_SERVICES` (Compose service names)
- `LAKE_ROOT` / `LAKE_HOST_PATH_*` (in `docker/.env`)
  - `LAKE_ROOT=/data_lake`
  - `LAKE_HOST_PATH_STAGING=/volume1/data_lake/staging`
  - `LAKE_HOST_PATH_PROD=/volume1/data_lake/prod`

Then reinstall hooks if you changed templates:

```bash
install -m 755 nas-hooks/post-receive.staging ~/git/bokser_app-staging.git/hooks/post-receive
install -m 755 nas-hooks/post-receive.production ~/git/bokser_app-production.git/hooks/post-receive
```

## 4) Prepare App Directories on NAS

Ensure each `APP_DIR` exists and contains:

- `docker/.env`
- `docker/docker-compose.yml`
- `docker/docker-compose.staging.yml` (staging only)
- `docker/docker-compose.prod.yml` (prod only)

Create data lake directories:

```bash
mkdir -p /volume1/data_lake/staging
mkdir -p /volume1/data_lake/prod
```

For local development on Windows, create:

```powershell
New-Item -ItemType Directory -Force C:\Users\erik\Code\data_lake\dev
```

## 5) Deploy Commands

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
