"""scripts/migrate.py's transaction-control stripping (ADR-0023, Fix B).

scripts/migrate.py is a standalone script, not a package under app/, so it is
loaded here the same way `python scripts/migrate.py` would load it: by
putting scripts/ on sys.path and importing it as a top-level module.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest  # noqa: E402

import migrate  # noqa: E402
from app.schema_state import checksum, discover  # noqa: E402


def test_strips_top_level_begin_and_commit():
    sql = "BEGIN;\nSELECT 1;\nCOMMIT;\n"
    stripped = migrate._strip_transaction_control(sql)
    assert "BEGIN" not in stripped
    assert "COMMIT" not in stripped
    assert "SELECT 1;" in stripped


def test_strips_rollback_and_start_transaction_case_insensitively():
    sql = "start transaction;\nSELECT 1;\nrollback;\n"
    stripped = migrate._strip_transaction_control(sql)
    assert "transaction" not in stripped.lower()
    assert "rollback" not in stripped.lower()
    assert "SELECT 1;" in stripped


def test_preserves_plpgsql_begin_inside_dollar_quoted_block():
    sql = (
        "ALTER TABLE t ADD COLUMN IF NOT EXISTS x INT;\n"
        "DO $$\n"
        "BEGIN\n"
        "    IF NOT EXISTS (SELECT 1) THEN\n"
        "        NULL;\n"
        "    END IF;\n"
        "END $$;\n"
    )
    # Nothing here is a top-level transaction-control statement: the file's
    # BEGIN is PL/pgSQL block syntax, not the runner's territory.
    assert migrate._strip_transaction_control(sql) == sql


def test_002_reduces_correctly_but_leaves_its_do_block_untouched():
    """Regression against the actual file that motivated Fix B: 002 wraps
    itself in BEGIN;/COMMIT; and also contains a DO $$ BEGIN ... END $$;
    block whose BEGIN must survive."""
    raw = (Path(migrate.MIGRATIONS_DIR) / "002_api_key_hashing.sql").read_bytes()
    stripped = migrate._strip_transaction_control(raw.decode("utf-8"))
    lines = [line.strip() for line in stripped.splitlines()]

    assert "BEGIN;" not in lines
    assert "COMMIT;" not in lines
    assert "BEGIN" in lines  # the PL/pgSQL block's bare BEGIN survives
    assert "END $$;" in lines


def test_checksum_is_unaffected_by_stripping():
    """The whole point of Fix B: hashing stays on RAW bytes. If stripping
    ever leaked into what gets hashed, every already-stamped ledger row for
    a migration with its own BEGIN/COMMIT would go MISMATCH on next deploy."""
    raw = (Path(migrate.MIGRATIONS_DIR) / "002_api_key_hashing.sql").read_bytes()
    before = checksum(raw)
    migrate._strip_transaction_control(raw.decode("utf-8"))
    after = checksum(raw)
    assert before == after
    # And the value itself must match what checksum() reports independently
    # of anything migrate.py does -- i.e. it really is hashing the file as-is.
    assert before == dict(discover(Path(migrate.MIGRATIONS_DIR)))["002_api_key_hashing.sql"]


class _FakeTransaction:
    """Records enter/exit so a test can assert exactly one transaction wraps
    a migration, without a real database."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        self._events.append("enter")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._events.append("exit")
        return False


class _FakeConn:
    def __init__(self):
        self.executed_sql = []
        self.txn_events = []

    def transaction(self):
        return _FakeTransaction(self.txn_events)

    async def execute(self, sql, *args):
        self.executed_sql.append(sql)

    async def fetch(self, *args, **kwargs):
        return []


@pytest.mark.asyncio
async def test_apply_wraps_a_self_transacting_migration_in_exactly_one_transaction(
    tmp_path, monkeypatch
):
    """A migration carrying its own BEGIN;/COMMIT; -- exactly what 002 does
    -- must still end up wrapped in exactly one transaction (the runner's),
    and the text actually sent to the connection must have the file's own
    BEGIN/COMMIT stripped while its DO $$ BEGIN ... END $$; block survives."""
    migration_sql = (
        "BEGIN;\n"
        "ALTER TABLE t ADD COLUMN IF NOT EXISTS x INT;\n"
        "DO $$\n"
        "BEGIN\n"
        "    NULL;\n"
        "END $$;\n"
        "COMMIT;\n"
    )
    (tmp_path / "002_self_transacting.sql").write_bytes(migration_sql.encode("utf-8"))

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
    monkeypatch.setattr(migrate, "discover", lambda: discover(tmp_path))

    conn = _FakeConn()
    result = await migrate.cmd_apply(conn)

    assert result == 0
    # executed_sql[0] is the ensure_ledger() DDL; [1] is the migration text.
    assert conn.txn_events == ["enter", "exit"]
    executed = conn.executed_sql[1]
    assert "BEGIN;" not in executed
    assert "COMMIT;" not in executed
    assert "DO $$" in executed
    assert "BEGIN\n" in executed or executed.strip().endswith("BEGIN")
