-- 002_key_requests.sql
-- Pending, unverified API-key requests. A row here is NOT a key: the real key is
-- only minted at verify-time and inserted into api_keys. This table holds just
-- enough to (a) email a verification link and (b) mint the right key on click.
--
-- The verify token is stored HASHED (same discipline as api_keys.key_hash): the
-- plaintext token travels only in the emailed link, so a DB dump does not hand
-- over working verification links.

CREATE TABLE IF NOT EXISTS key_requests (
    id             SERIAL PRIMARY KEY,
    email          VARCHAR(255) NOT NULL,
    name           VARCHAR(255),
    use_case       TEXT,
    tier           VARCHAR(20)  NOT NULL DEFAULT 'free',
    daily_limit    INTEGER      NOT NULL DEFAULT 1000,
    token_hash     VARCHAR(64)  NOT NULL UNIQUE,          -- sha256 hex of verify token
    source_ip      VARCHAR(64),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours'),
    consumed_at    TIMESTAMPTZ,                            -- set on successful verify; blocks reuse
    email_sent_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_key_requests_email   ON key_requests (email);
CREATE INDEX IF NOT EXISTS ix_key_requests_created ON key_requests (created_at);
