#!/usr/bin/env bash
#
# Daily database backup + log retention for LexicRo.
#
# Install: nothing to copy. cron runs this in place from the checkout at
# /opt/lexicro/scripts/. Create the dump directory once:
#   sudo mkdir -p /var/backups/lexicro
#
# Schedule: scripts/crontab in this repo is the single source of truth --
#   sudo crontab /opt/lexicro/scripts/crontab
# It runs at 03:17, an odd minute so it does not collide with everything else
# on the host that fires at exactly 03:00.
#
# This header used to describe installing to /usr/local/bin/lexicro-backup and
# carried a third, different cron line. That install was never done and the host
# has always run the script from the checkout; both are corrected here.
#
# Design notes:
#   * `set -euo pipefail` so a failure stops the script instead of quietly
#     rotating away good backups and leaving nothing behind.
#   * The new dump is verified BEFORE old ones are deleted. A backup routine
#     that prunes first and dumps second can leave you with zero backups.
#   * Output is plain SQL, gzipped: readable, greppable, restorable anywhere,
#     and not tied to this Postgres build.
#   * Backups live on the same disk as the data, so this alone does not protect
#     against disk loss. Pair it with Hetzner's automated backups (20% of server
#     price) or copy off-box.

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/lexicro}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/lexicro}"
KEEP_DAYS="${KEEP_DAYS:-14}"           # keep this many days of dumps
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-90}"   # prune request_log beyond this
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-lexicro}"
MIN_BYTES="${MIN_BYTES:-200}"          # floor: catches a totally empty file
# A byte count is a poor health check -- this database gzips to well under a
# kilobyte, so a size threshold would reject perfectly good backups. Verify the
# dump CONTAINS what it should instead; that holds at any database size.
EXPECT_TABLE="${EXPECT_TABLE:-api_keys}"

# cron runs with a minimal PATH; docker-compose usually is not on it.
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

log() { printf '%s  %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*"; }
die() { log "ERROR: $*"; exit 1; }

# Read one KEY=value out of a .env file. Deliberately not `source`: .env is
# consumed by docker compose, not bash, so sourcing it under `set -e` would let
# one stray character in an unrelated variable abort the backup. Takes the last
# occurrence, strips a trailing CR and one layer of surrounding quotes.
get_env_value() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$2" \
        | tail -n 1 \
        | tr -d '\r' \
        | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

command -v docker-compose >/dev/null 2>&1 || die "docker-compose not found on PATH"
cd "$COMPOSE_DIR" || die "cannot cd to $COMPOSE_DIR"
mkdir -p "$BACKUP_DIR"

STAMP="$(date -u '+%Y%m%d-%H%M%S')"
TARGET="${BACKUP_DIR}/lexicro-${STAMP}.sql.gz"

log "starting backup -> ${TARGET}"

# --- dump ------------------------------------------------------------------
# -T: no TTY (cron has none). Write to a .partial name so an interrupted run
# never leaves a truncated file that looks like a valid backup.
if ! docker-compose exec -T "$DB_SERVICE" \
        pg_dump -U "$DB_USER" "$DB_NAME" 2>/dev/null | gzip > "${TARGET}.partial"; then
    rm -f "${TARGET}.partial"
    die "pg_dump failed"
fi

SIZE="$(stat -c %s "${TARGET}.partial" 2>/dev/null || echo 0)"
[ "$SIZE" -ge "$MIN_BYTES" ] || { rm -f "${TARGET}.partial"; die "dump only ${SIZE} bytes -- refusing"; }

# The gzip stream must be intact...
gzip -t "${TARGET}.partial" || { rm -f "${TARGET}.partial"; die "gzip verification failed"; }

# ...and it must actually contain the schema. This is the check that matters:
# a dump that ran against the wrong database, or died after the header, passes
# every size and checksum test while being useless.
#
# Count matches rather than `grep -q`. Under `set -o pipefail`, `grep -q` exits
# the moment it finds the match, gunzip takes SIGPIPE writing into the closed
# pipe and returns 141, and pipefail promotes that to the pipeline's status --
# so a perfectly good dump is read as "table missing" and deleted. It bites only
# once the dump outgrows the pipe buffer, because until then gunzip has finished
# writing before grep quits: this passed for months, then failed every night
# from 2026-08-26, when request_log grew past ~64K of decompressed output.
# `grep -c` reads to EOF, so there is no early exit and no signal. `|| true`
# keeps a legitimate no-match (grep exits 1) from tripping `set -e`.
MATCHES="$(gunzip -c "${TARGET}.partial" | grep -ci "CREATE TABLE.*${EXPECT_TABLE}" || true)"
if [ "${MATCHES:-0}" -eq 0 ]; then
    rm -f "${TARGET}.partial"
    die "dump does not contain the ${EXPECT_TABLE} table -- refusing"
fi

mv "${TARGET}.partial" "$TARGET"
log "backup ok: $(du -h "$TARGET" | cut -f1)"

# --- prune old dumps (only AFTER a good one exists) -------------------------
DELETED="$(find "$BACKUP_DIR" -name 'lexicro-*.sql.gz' -mtime "+${KEEP_DAYS}" -print -delete | wc -l)"
[ "$DELETED" -gt 0 ] && log "pruned ${DELETED} dump(s) older than ${KEEP_DAYS} days"

REMAINING="$(find "$BACKUP_DIR" -name 'lexicro-*.sql.gz' | wc -l)"
log "${REMAINING} backup(s) on disk, $(du -sh "$BACKUP_DIR" | cut -f1) total"

# --- request_log retention --------------------------------------------------
# The table grows monotonically and is only read for rate limiting, which cares
# about today. Without this it is unbounded.
PRUNED="$(docker-compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "DELETE FROM request_log WHERE requested_at < NOW() - INTERVAL '${LOG_RETENTION_DAYS} days';" \
    2>/dev/null | tr -dc '0-9' || true)"
log "request_log: pruned ${PRUNED:-0} row(s) older than ${LOG_RETENTION_DAYS} days"

# --- optional dead-man's switch ---------------------------------------------
# If HEALTHCHECK_URL is set, ping it on success. If the backup stops running --
# cron broken, disk full, host down -- the service notices the silence and
# emails you. A backup you never check is a backup you do not have.
#
# The URL is a capability: anyone holding it can mark this check healthy, which
# would mask a backup that had silently stopped. It therefore lives in .env with
# the other secrets, NOT inline in the crontab line -- a crontab line gets read
# aloud, pasted into issues and copied into runbooks, and this one leaked twice
# that way before it was moved here.
#
# An env var set by the caller still wins, so an older inline-crontab line keeps
# working unchanged.
if [ -z "${HEALTHCHECK_URL:-}" ] && [ -r "${COMPOSE_DIR}/.env" ]; then
    HEALTHCHECK_URL="$(get_env_value HEALTHCHECK_URL "${COMPOSE_DIR}/.env")"
fi

if [ -n "${HEALTHCHECK_URL:-}" ]; then
    curl -fsS -m 10 --retry 3 "$HEALTHCHECK_URL" >/dev/null 2>&1 \
        && log "pinged healthcheck" \
        || log "WARNING: healthcheck ping failed"
fi

log "done"
