#!/bin/bash
set -euo pipefail

cd /opt/lexicro
git pull

# Bring the database up alone and apply any pending migrations BEFORE the API
# starts. The API refuses to serve a database behind its own migrations
# (ADR-0023), so this ordering is load-bearing, not tidiness.
docker compose up -d db
docker compose run --rm api python scripts/migrate.py --apply

# v1.29.2 ContainerConfig workaround, retained deliberately -- see ADR-0004.
docker compose rm -f api
docker compose up -d

echo "Deployed successfully"
