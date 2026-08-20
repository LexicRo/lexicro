# Unattended-operation checklist

Everything needed for the deployment to survive a fortnight without anyone
watching it. Ordered by what breaks worst if skipped.

---

## 1. Restart policies — the one that actually matters

Neither container currently has a `restart:` policy. **If the host reboots for
any reason — kernel update, Hetzner maintenance, an OOM — nothing comes back
up.** The API stays down until someone logs in.

In `docker-compose.yml`, add one line to **each** service:

```yaml
services:
  db:
    image: postgres:18
    restart: unless-stopped          # <-- add
    environment:
      ...

  api:
    build: .
    restart: unless-stopped          # <-- add
    ports:
      ...
```

`unless-stopped` rather than `always`: if you deliberately stop a container to
work on something, it stays stopped across a reboot instead of surprising you by
coming back.

Verify it survives a real reboot rather than trusting the config:

```bash
docker-compose up -d
sudo reboot
# wait ~60s, then from your machine:
curl.exe -s -o NUL -w "%{http_code}`n" https://api.lexicro.com/health
```

---

## 2. Log rotation — unbounded by default

Docker's `json-file` driver keeps container logs forever. Slow, but it only ends
one way: a full disk, which takes the database down with it.

Add to **each** service in `docker-compose.yml`:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Caps each container at 30 MB. Applies to newly created containers, so it takes
effect on the next `docker-compose up -d --build`.

Check what has already accumulated:

```bash
du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail
```

---

## 3. Database backups

```bash
sudo mkdir -p /var/backups/lexicro

# run once by hand -- catches wrong paths or service names immediately
sudo bash /opt/lexicro/scripts/backup.sh
ls -lh /var/backups/lexicro/
```

Then schedule it:

```bash
sudo crontab -e
```

```cron
17 3 * * * /bin/bash /opt/lexicro/scripts/backup.sh >> /var/log/lexicro-backup.log 2>&1
```

An odd minute, deliberately: everything on a default Linux box runs at exactly
03:00.

**Prove a restore works.** An untested backup is a hope, not a backup:

```bash
gunzip -c /var/backups/lexicro/lexicro-*.sql.gz | head -40
gunzip -c /var/backups/lexicro/lexicro-*.sql.gz | grep -c "INSERT\|COPY"
```

You want to see the schema and your `api_keys` rows.

### Hetzner automated backups

Worth enabling alongside, at **20% of the server price** (~€1.20–1.60/month for
a box this size, up to 7 retained). Console → your server → Backups.

They cover different failures. The Hetzner image restores the whole machine
after disk loss or a botched upgrade. The `pg_dump` is a readable SQL file you
can inspect, partially restore, or move to another host — which is what you
actually reach for when the problem is "I deleted the wrong rows".

Both, given the price.

---

## 4. Monitoring — otherwise "down" means "down until I check"

The script cannot monitor the host it runs on. Use something external.

**API uptime.** Any free uptime monitor (UptimeRobot, Better Stack, Hetzner's
own) pointed at:

```
https://api.lexicro.com/health
```

Five-minute interval, email alert. Five minutes of setup.

**Backups still running.** Create a check at healthchecks.io (free), then:

```bash
sudo crontab -e
```

```cron
17 3 * * * HEALTHCHECK_URL=https://hc-ping.com/your-uuid /bin/bash /opt/lexicro/scripts/backup.sh >> /var/log/lexicro-backup.log 2>&1
```

The script pings on success. If backups stop — cron broken, disk full, host
gone — the silence is what triggers the alert. Failure modes that produce no
output are exactly the ones you otherwise discover far too late.

---

## 5. Certificate renewal

If TLS is Let's Encrypt via certbot, renewal is usually automatic — but confirm
it, because an expired certificate two weeks into a holiday breaks everything
including your own ability to check on it:

```bash
systemctl list-timers | grep -i certbot
sudo certbot certificates          # look at the expiry date
```

If the expiry falls inside your time away and no timer is active, renew now:

```bash
sudo certbot renew --dry-run
```

---

## 6. Disk headroom

```bash
df -h /
docker system df
```

You had 68 GB free, so this is comfortable. If images have accumulated from
repeated rebuilds:

```bash
docker image prune -f
```

---

## Before you go — five commands

```bash
docker-compose ps                                    # both Up, db healthy
sudo bash /opt/lexicro/scripts/backup.sh                   # backup works
sudo crontab -l                                      # cron installed
df -h / && free -m                                   # disk and memory headroom
curl -s -o /dev/null -w "%{http_code}\n" https://api.lexicro.com/health
```

And one from your own machine, to confirm it works from outside:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://api.lexicro.com/guide
```

---
## Recreating the db container — known compose bug

`docker-compose` 1.29.2 fails with `KeyError: 'ContainerConfig'` when recreating
a container against a newer Docker Engine image format. It appears whenever a
change touches the `db` service.

Workaround — take a dump first, then force removal rather than in-place recreate:

    docker-compose exec -T db pg_dump -U postgres lexicro | gzip > /root/pre-change.sql.gz
    docker-compose rm -sf db api
    docker-compose up -d

Data lives in the named volume `postgres_data`, which `rm` does not touch.

Root cause: compose v1 (Python) is end-of-life. The v2 plugin — `docker compose`,
with a space — does not have this bug and is a drop-in for this compose file.
Worth migrating when there is time to test it properly.


## Deliberately not doing before leave

**The relative-rules lemma retrain.** It is the right fix and it is ready, but
deploying a new model the day before two weeks away is how you return to a
subtle regression nobody was watching. The current model is measured, deployed
and behaving. It keeps.

## Database migrations

Schema changes ship as numbered files in `migrations/`, applied in filename
order and recorded in a `schema_migrations` table. `deploy.sh` applies pending
migrations before the API starts, and **the API refuses to serve a database
behind the migrations in its own image** — a crash-loop, deliberately, so the
`/health` monitor turns it into an alert.

Check state at any time, read-only and safe on a live service:

```bash
docker compose run --rm api python scripts/migrate.py --status
```

`docker compose run` overrides the image's command, so this does not start the
API and does not trigger the startup gate.

**Migrations are append-only.** Never edit one that has been applied anywhere —
the ledger stores a checksum, and an edit becomes a fatal startup error. To
correct a mistake, add a new migration.

**A migration file must not contain its own `BEGIN`/`COMMIT`/`ROLLBACK`.** The
runner wraps every file in exactly one transaction (`--apply` opens it, runs
the whole file, then records the ledger row, all inside that same
transaction). A file that opens its own transaction breaks that silently: run
inside the runner's transaction, the file's `BEGIN` is a no-op warning and its
`COMMIT` ends the runner's transaction early, so the ledger `INSERT` that
follows lands in a separate implicit transaction instead of the migration's
own. `--apply` strips a file's own top-level `BEGIN`/`COMMIT`/`ROLLBACK`/
`START TRANSACTION` line only when that line consists of the bare keyword
alone (optionally followed by `;`) and nothing else — for example a line
that is just `BEGIN;` (a `DO $$ BEGIN ... END $$;` block is left alone —
that `BEGIN` is PL/pgSQL, not transaction control). Anything more elaborate
is **not** stripped — `BEGIN TRANSACTION;`, `COMMIT WORK;`, `START
TRANSACTION ISOLATION LEVEL SERIALIZABLE;`, the bare `END;` COMMIT synonym,
and multiple transaction-control statements packed onto one line (`BEGIN;
SELECT 1; COMMIT;`) all survive stripping untouched. Rather than proceed
with one of those still in the file, `--apply` re-scans the stripped text
and **refuses to apply that migration** — reporting the file, the offending
line, and this rule — so don't rely on the stripping at all: write new
migrations without their own transaction control in the first place.

### Adopting an existing database (once per database)

A database that predates this mechanism has the schema but no ledger. Stamp it
without re-running anything:

```bash
git pull
docker compose build api                                             # 1. the script lives in the NEW image
docker compose run --rm api python scripts/migrate.py --status       # 2. confirm: empty ledger, 3 pending
docker compose exec db psql -U postgres -d lexicro                   # 3. inspect the actual schema
docker compose run --rm api python scripts/migrate.py --baseline 003 # 4. stamp -- use the number the inspection gave you
./deploy.sh                                                          # 5. only now
```

**The build in step 1 is not optional** — the currently-running image does not
contain `scripts/migrate.py`. And the order matters: deploying the gated image
before stamping leaves an empty ledger, so the API sees three missing
migrations and crash-loops until someone stamps it.

**Step 2 tells you the ledger is empty. It does not tell you what to baseline
to.** `--status` diffs the ledger table against the `migrations/` directory —
filenames and checksums only. It never looks at a table or a column, so
"empty ledger, 3 pending" is what it prints for *any* unbaselined database,
regardless of what schema that database actually has. The command that can be
wrong here is `--baseline`, and nothing about `--status` can catch it.

**Step 3 is the check that actually matters.** Look at what the database has
and match it against the table below — derived from what each migration file
creates, not from an assumption:

| Observed schema | Baseline | Why |
|---|---|---|
| `api_keys` has `key_hash`/`key_prefix`/`revoked_at` (no plaintext `key` column) **and** `key_requests` exists | `--baseline 003` | All three migrations' changes are present |
| `api_keys` has `key_hash`/`key_prefix`/`revoked_at` (no plaintext `key` column), but `key_requests` does **not** exist | `--baseline 002` | 001 and 002 are present; `deploy.sh`'s `--apply` will then run 003 |
| `api_keys` still has a plaintext `key` column | `--baseline 001` | Only the initial schema is present; `--apply` will then run 002 and 003 |

In `psql`:

```sql
\d api_keys
\dt key_requests
```

Baselining too high silently skips a migration that will then never run —
that is exactly what step 3 exists to prevent. `--status` cannot see it;
only looking at the schema itself can.

**Step 5 recreates the `db` container — take a dump first.** This branch
drops the `./init.sql:/docker-entrypoint-initdb.d/init.sql` bind mount from
the `db` service (migrations replaced it, see ADR-0023). Compose keys
recreation off the service config hash, so the first `docker compose up -d
db` after this change — the one inside `deploy.sh`, i.e. step 5 above —
recreates the `db` container. The data itself is safe: it lives in the named
`postgres_data` volume, and the mount that was removed was a read-only bind
consumed only at `initdb`. Take a dump before running step 5 anyway, using
the same `pg_dump` invocation as the "Recreating the db container" section
above:

```bash
docker-compose exec -T db pg_dump -U postgres lexicro | gzip > /root/pre-change.sql.gz
```

Expect a short API blip when the container bounces: `app/database.py`
builds its SQLAlchemy engine without `pool_pre_ping`, so the running API's
already-pooled connections go stale across the restart until the API's own
container is recreated a moment later in the same step.

### When something goes wrong

**A failed `--apply` during deploy does not take the API down.** In
`deploy.sh`, `set -euo pipefail` halts the script the moment
`migrate.py --apply` exits non-zero — before `docker compose rm -f api` and
`up -d`. The previously running API container was never touched and keeps
serving on the old (still schema-consistent) image. A failed deploy leaves
you exactly where you started, not mid-air; fix the migration and re-run
`./deploy.sh` when ready.

**If the startup gate fires in production**, the API container will
crash-loop (`restart: unless-stopped` keeps retrying it), and that crash loop
*is* the alert — the `/health` monitor will fire because the container never
comes up healthy. Diagnose without touching the crash-looping container:

```bash
docker compose run --rm api python scripts/migrate.py --status
```

This runs in a fresh one-off container and overrides the image's command, so
it never triggers the gate itself. Read what it reports:

- **`PENDING`** — the image shipped a migration the database doesn't have
  yet. Run `docker compose run --rm api python scripts/migrate.py --apply`.
  This is the ordinary case: `deploy.sh` should have done this already, so
  seeing it here means the apply step itself failed or was skipped — check
  the deploy log.
- **`MISMATCH`** — an applied migration's file no longer matches what was
  recorded when it ran. Migrations are append-only; find out what changed
  (`git log -p -- migrations/<file>`) and either revert the edit, or, if the
  edit was deliberate, restamp past it:
  `docker compose run --rm api python scripts/migrate.py --restamp N` — never
  just re-run it. **Use `--restamp`, not `--baseline`, for this.**
  `--baseline` inserts `ON CONFLICT DO NOTHING`, so it leaves a row that
  already exists with its old, mismatched checksum untouched and reports
  success anyway — it cannot repair a `MISMATCH`. `--restamp` overwrites the
  recorded checksum with what's on disk now, which is the actual repair, and
  it says plainly at the confirmation prompt which files' checksums are
  about to be overwritten. **`N` is the number of the mismatched file
  itself** — e.g. if `--status` reports `002` as `MISMATCH`, run `--restamp
  002`, not the highest migration number in the tree. `--restamp` (like
  `--baseline`) stamps every migration with prefix `<= N` as applied,
  inserting fresh ledger rows for any of them that are genuinely still
  `PENDING`. Passing a higher `N` than the mismatched file — for example
  reusing `003` from the adoption example above — silently marks a pending
  `003` as applied without ever running it.
- **`up to date` with no `PENDING`/`MISMATCH`** but the gate still fired —
  the schema changed underneath the ledger (a manual `psql` change, a restore
  from an out-of-band backup). Compare the live schema against the migration
  files by hand.

**The startup gate runs a real database query before the app will start.**
Since `lifespan` opens a session and reads `schema_migrations` before
`yield`-ing, a transient database outage doesn't degrade the API — it
prevents it from starting at all, so `/health` is unreachable rather than
returning `{"status": "ok"}`. With `depends_on: service_healthy` and
`restart: unless-stopped` the API comes back on its own once `db` is healthy
again, but an uptime monitor watching `/health` will see a hard outage where
it used to see a healthy response, not a degraded one — keep that in mind
when reading an alert.

**Rollback.** `app/schema_state.py` treats migrations that are in the
database but not in the image (`ahead`) as a warning, not a refusal —
deliberately, per `SchemaState.ok`, "refusing would make rolling the
application back impossible." That means rolling the app back to an older
image is safe with respect to the gate: an older image will log a warning
about migrations it doesn't recognise and serve anyway, rather than
crash-loop. What it will *not* do is undo those migrations' schema changes
or make the older code aware of them — this mechanism has no `down`
migrations. If a migration is destructive (a dropped or renamed column an
older code path still reads), rolling the image back does not undo the
danger; you need a new forward migration or a restore from backup, not a
downgrade.
