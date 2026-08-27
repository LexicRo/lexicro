#!/usr/bin/env bash
#
# Probe the public API and report to its own healthchecks.io check.
#
# Install: nothing to copy. cron runs this in place from the checkout at
# /opt/lexicro/scripts/, alongside backup.sh. scripts/crontab is the single
# source of truth for the schedule.
#
# WHY THIS EXISTS
#
# Until 2026-08-26 the only healthchecks.io check on this host was pinged from
# inside backup.sh, while being named "LexicRo Health" and tagged
# `api database health service`. It reported one fact -- whether last night's
# dump finished -- and would have stayed green through a total API outage. On
# 2026-08-26 it went red for a backup problem while the API was serving happily,
# which is the same defect seen from the other side.
#
# So: backup.sh watches the backup, this watches the API, and each pings its own
# check. Neither can speak for the other.
#
# WHY A CRON JOB RATHER THAN AN UPTIME SERVICE
#
# healthchecks.io does not poll -- it waits to be pinged and complains about
# silence. Something has to do the requesting, and a cron job on this host is
# enough to catch a dead host: if the box is down, cron never runs, no ping
# arrives, and the dead man's switch fires. That is the same mechanism that
# already protects the backup.
#
# WHAT THIS STILL CANNOT SEE, and it is worth being honest about it: the probe
# runs FROM the host, so it cannot distinguish "the API is down" from "this
# host's outbound network is broken", and it will not notice the API being
# unreachable from the wider internet while reachable from Nuremberg. Only a
# third-party poller fixes that. This is the cheap 90%, not the whole thing.
#
# WHAT "HEALTHY" MEANS HERE, and its limit. /health is unauthenticated. Since
# 0.6.2 it also makes a bounded SELECT 1 and returns 503 when that fails
# (ADR-0028, closing OQ-022), so the -f below now catches a database outage as
# well as a dead process, a broken nginx or an expired certificate. That is why
# this script needed no change when the endpoint deepened: the status code was
# always the signal.
#
# What it still does NOT prove: that the API can serve a KEYED request.
# Authentication and the daily quota read api_keys through the rate limiter,
# and nothing here exercises that path -- deliberately, since probing it would
# cost quota, put a working key on this host, and pollute request_log with
# synthetic traffic. Read a green check as "serving, and the database answers",
# not as "everything works".

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/lexicro}"

# The PUBLIC hostname on purpose. Hitting 127.0.0.1:8001 would test only the
# container and skip everything that has actually broken here before: DNS, the
# Hetzner Cloud Firewall, nginx, and the certificate.
PROBE_URL="${PROBE_URL:-https://api.lexicro.com/health}"

# cron runs with a minimal PATH.
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

log() { printf '%s  %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*"; }

# Same reader as backup.sh, deliberately duplicated rather than shared: these
# are two independent cron jobs, and a common library would mean a syntax error
# in one file silently stopping both. Six lines is a cheaper price than that
# coupling. Takes the last occurrence, strips a trailing CR and one layer of
# surrounding quotes.
get_env_value() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$2" \
        | tail -n 1 \
        | tr -d '\r' \
        | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

# -f makes curl exit non-zero on 4xx/5xx, so a 502 from nginx counts as a
# failure rather than a successful fetch of an error page.
if ! curl -fsS -m 15 "$PROBE_URL" >/dev/null 2>&1; then
    log "PROBE FAILED: ${PROBE_URL} did not return success -- not pinging"
    # Exit non-zero so the failure is visible in cron mail and the log, and so
    # the check is NOT pinged. Silence is the signal.
    exit 1
fi

# The URL is a capability: anyone holding it can mark this check healthy, which
# would mask an outage. It lives in .env with the other secrets, never inline in
# the crontab -- a crontab line gets read aloud, pasted into issues and copied
# into runbooks, and the backup one leaked twice that way before it was moved.
if [ -z "${API_HEALTHCHECK_URL:-}" ] && [ -r "${COMPOSE_DIR}/.env" ]; then
    API_HEALTHCHECK_URL="$(get_env_value API_HEALTHCHECK_URL "${COMPOSE_DIR}/.env")"
fi

if [ -z "${API_HEALTHCHECK_URL:-}" ]; then
    # Not fatal: the probe itself still works and still logs. But say so, or a
    # check nobody set up looks identical to a check that is passing.
    log "probe ok, but API_HEALTHCHECK_URL is not set -- nothing to ping"
    exit 0
fi

curl -fsS -m 10 --retry 3 "$API_HEALTHCHECK_URL" >/dev/null 2>&1 \
    && log "probe ok, pinged api healthcheck" \
    || log "probe ok, but WARNING: api healthcheck ping failed"
