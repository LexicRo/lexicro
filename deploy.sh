#!/bin/bash
set -euo pipefail

cd /opt/lexicro
git pull

# The Dockerfile COPYs the repo into the image (COPY . .) and nothing bind-mounts
# source over it, so the image on disk is whatever `git pull` last built --- not
# whatever `git pull` just fetched. Skip this and `migrate.py --apply` below runs
# inside the STALE image, discover()-ing the stale image's migrations/ directory,
# and reports "Nothing to apply" even though a new migration just landed on the
# host. The gate then compares that same stale image against the ledger and finds
# them consistent: the migration is silently never applied and never detected.
# The image must be current before anything downstream reads migrations out of it.
docker compose build api

# Bring the database up alone and apply any pending migrations BEFORE the API
# starts. The API refuses to serve a database behind its own migrations
# (ADR-0023), so this ordering is load-bearing, not tidiness.
docker compose up -d db
docker compose run --rm api python scripts/migrate.py --apply

# v1.29.2 ContainerConfig workaround, retained deliberately -- see ADR-0004.
docker compose rm -f api
docker compose up -d

echo "Deployed successfully"
