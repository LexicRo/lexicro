-- 002_api_key_hashing.sql
--
-- Store a SHA-256 of each API key instead of the key itself.
--
-- Why a plain fast hash rather than bcrypt/argon2: unlike a password, an API
-- key is 256 bits of CSPRNG output. There is no dictionary to attack and no
-- realistic brute force, so key-stretching buys nothing and would add latency
-- to every single request. A fast hash keeps lookup a single indexed query.
--
-- Consequence, and it is a product decision as much as a security one: once
-- issued, a key can never be shown again. Same behaviour as GitHub and Stripe,
-- and what developers now expect. `key_prefix` stays in plaintext so keys are
-- identifiable in support conversations and dashboards without being usable.
--
-- Run inside a transaction; safe to re-run (all steps are guarded).

BEGIN;

-- ---------------------------------------------------------------- api_keys

ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_hash    VARCHAR(64);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix  VARCHAR(16);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS label       VARCHAR(100);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS revoked_at   TIMESTAMPTZ;

-- Backfill from any existing plaintext keys. pgcrypto gives us sha256() in SQL
-- so the old values never have to leave the database to be migrated.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE api_keys
   SET key_hash   = encode(digest(key, 'sha256'), 'hex'),
       key_prefix = left(key, 12)
 WHERE key_hash IS NULL
   AND key IS NOT NULL;

-- Enforce the invariants only after backfilling.
ALTER TABLE api_keys ALTER COLUMN key_hash SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'api_keys_key_hash_key'
    ) THEN
        ALTER TABLE api_keys ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);
    END IF;
END $$;

-- The plaintext column is now redundant. Dropping it is the entire point of the
-- migration -- leave it in place and a database dump still leaks every key.
ALTER TABLE api_keys DROP COLUMN IF EXISTS key;

-- ------------------------------------------------------------- request_log

-- The log stored the raw key too, which is a second plaintext copy in a table
-- that usually has looser access controls than api_keys. Store the hash.
ALTER TABLE request_log ADD COLUMN IF NOT EXISTS key_hash VARCHAR(64);

UPDATE request_log
   SET key_hash = encode(digest(api_key, 'sha256'), 'hex')
 WHERE key_hash IS NULL
   AND api_key IS NOT NULL;

ALTER TABLE request_log DROP COLUMN IF EXISTS api_key;

-- Rate limiting counts rows per key within a time window on EVERY request.
-- Without this index that is a sequential scan over a table that grows forever:
-- fast today, progressively slower every day. Composite and in this order
-- because the query filters on both and ranges over the timestamp.
CREATE INDEX IF NOT EXISTS request_log_key_time_idx
    ON request_log (key_hash, requested_at DESC);

-- Housekeeping: without retention this table is unbounded. Uncomment once you
-- have decided how long request history is worth keeping.
-- DELETE FROM request_log WHERE requested_at < NOW() - INTERVAL '90 days';

COMMIT;
