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


@pytest.mark.asyncio
async def test_checksum_is_unaffected_by_stripping(tmp_path, monkeypatch):
    """The whole point of Fix B: the ledger's checksum column stays bound to
    RAW bytes, never to the stripped text. If cmd_apply's ledger INSERT ever
    hashed the stripped text instead, every already-stamped migration with
    its own BEGIN/COMMIT would flip to MISMATCH on the next deploy (checksum()
    itself, and --status's diff() against it, always hash the file as-is).

    This must drive cmd_apply, not just call checksum() on immutable bytes
    around a discarded return value -- that shape can never fail, so it
    would never have caught the exact regression this test guards against
    (checksum(raw) -> checksum(executable.encode("utf-8")) in cmd_apply's
    ledger insert). A migration fixture with its own BEGIN;/COMMIT; is
    required so the two checksums actually differ; otherwise this would
    pass even against that regression by coincidence.
    """
    migration_sql = "BEGIN;\nALTER TABLE t ADD COLUMN IF NOT EXISTS x INT;\nCOMMIT;\n"
    raw = migration_sql.encode("utf-8")
    (tmp_path / "002_self_transacting.sql").write_bytes(raw)

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
    monkeypatch.setattr(migrate, "discover", lambda: discover(tmp_path))

    stripped = migrate._strip_transaction_control(migration_sql)
    assert stripped != migration_sql  # fixture must actually exercise stripping
    assert checksum(raw) != checksum(stripped.encode("utf-8"))  # and diverge once hashed

    conn = _FakeConn()
    result = await migrate.cmd_apply(conn)
    assert result == 0

    insert_calls = [
        (sql, args) for sql, args in conn.executed_calls
        if "INSERT INTO schema_migrations" in sql
    ]
    assert len(insert_calls) == 1
    _, insert_args = insert_calls[0]
    name, bound_checksum, _version = insert_args

    assert name == "002_self_transacting.sql"
    assert bound_checksum == checksum(raw)
    assert bound_checksum != checksum(stripped.encode("utf-8"))
    # And matches what checksum() reports independently via discover(), i.e.
    # it really is hashing the file as raw bytes, the same as --status does.
    assert bound_checksum == dict(discover(tmp_path))["002_self_transacting.sql"]


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
        self.executed_calls = []  # (sql, args) for every execute() call, in order
        self.txn_events = []

    def transaction(self):
        return _FakeTransaction(self.txn_events)

    async def execute(self, sql, *args):
        self.executed_sql.append(sql)
        self.executed_calls.append((sql, args))

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


# _strip_transaction_control only removes a bare keyword alone on its own
# line. These five forms survive stripping untouched and each would
# silently reinstate the "runner's transaction gets cut short" bug Fix B
# closed -- so cmd_apply must refuse to apply a file containing any of them,
# rather than run it as if it were runner-safe.
_UNSTRIPPABLE_TXN_CONTROL_FORMS = [
    pytest.param("BEGIN TRANSACTION;\nSELECT 1;\n", id="begin_transaction"),
    pytest.param("SELECT 1;\nCOMMIT WORK;\n", id="commit_work"),
    pytest.param(
        "START TRANSACTION ISOLATION LEVEL SERIALIZABLE;\nSELECT 1;\n",
        id="start_transaction_isolation_level",
    ),
    pytest.param(
        "ALTER TABLE t ADD COLUMN IF NOT EXISTS x INT;\nEND;\n",
        id="bare_end_commit_synonym",
    ),
    pytest.param("BEGIN; SELECT 1; COMMIT;\n", id="multiple_statements_one_line"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("migration_sql", _UNSTRIPPABLE_TXN_CONTROL_FORMS)
async def test_apply_refuses_residual_transaction_control(
    tmp_path, monkeypatch, migration_sql
):
    (tmp_path / "002_bad.sql").write_bytes(migration_sql.encode("utf-8"))
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
    monkeypatch.setattr(migrate, "discover", lambda: discover(tmp_path))

    conn = _FakeConn()
    result = await migrate.cmd_apply(conn)

    assert result == 1
    # The migration's own SQL must never have reached conn.execute(): the
    # refusal is a pre-flight check before anything is applied. Only the
    # ensure_ledger() DDL call is allowed through.
    assert conn.executed_sql == [migrate.LEDGER_DDL]
    assert conn.txn_events == []


def test_residual_transaction_control_reports_correct_line_number():
    sql = "ALTER TABLE t ADD COLUMN IF NOT EXISTS x INT;\nEND;\n"
    violation = migrate._residual_transaction_control(sql)
    assert violation is not None
    line_no, stmt_text = violation
    assert line_no == 2
    assert stmt_text == "END;"


@pytest.mark.asyncio
async def test_apply_still_applies_the_real_002_cleanly(monkeypatch):
    """002_api_key_hashing.sql is the actual file that motivated Fix B: it
    wraps itself in BEGIN;/COMMIT; (stripped) and contains a genuine
    DO $$ BEGIN ... END $$; block (must survive both stripping and the new
    residual-transaction-control refusal). Run cmd_apply against the real
    migrations directory to prove the refusal check has no false positive
    on it."""
    conn = _FakeConn()
    result = await migrate.cmd_apply(conn)

    assert result == 0
    applied_names = [call[1][0] for call in conn.executed_calls
                     if "INSERT INTO schema_migrations" in call[0]]
    assert "002_api_key_hashing.sql" in applied_names
