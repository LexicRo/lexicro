CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(64) UNIQUE NOT NULL,
    email       VARCHAR(255),
    tier        VARCHAR(20) DEFAULT 'free',
    daily_limit INTEGER DEFAULT 1000,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS request_log (
    id           SERIAL PRIMARY KEY,
    api_key      VARCHAR(64),
    ip_address   VARCHAR(45),
    endpoint     VARCHAR(100),
    requested_at TIMESTAMPTZ DEFAULT NOW()
);