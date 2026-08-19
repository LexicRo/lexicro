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

### Adopting an existing database (once per database)

A database that predates this mechanism has the schema but no ledger. Stamp it
without re-running anything:

```bash
git pull
docker compose build api                                            # 1. the script lives in the NEW image
docker compose run --rm api python scripts/migrate.py --status      # 2. confirm: empty ledger, 3 pending
docker compose run --rm api python scripts/migrate.py --baseline 003 # 3. stamp
./deploy.sh                                                          # 4. only now
```

**The build in step 1 is not optional** — the currently-running image does not
contain `scripts/migrate.py`. And the order matters: deploying the gated image
before stamping leaves an empty ledger, so the API sees three missing
migrations and crash-loops until someone stamps it.

Steps 1-3 are safe on a live service. `docker compose run` overrides the
image's command, so the API never starts and the gate never fires; the previous
container keeps serving until step 4.

Baselining too high silently skips a migration that will then never run.
Always `--status` first.
