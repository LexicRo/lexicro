"""The startup gate refuses to serve a database it does not recognise (ADR-0023)."""

import asyncpg
import pytest
from sqlalchemy.exc import ProgrammingError

from app.main import _read_ledger, verify_schema


def test_serves_when_ledger_matches(monkeypatch):
    monkeypatch.setattr(
        "app.main.discover", lambda: [("001_a.sql", "aaa"), ("002_b.sql", "bbb")]
    )
    verify_schema({"001_a.sql": "aaa", "002_b.sql": "bbb"})  # must not raise


def test_refuses_when_database_is_behind(monkeypatch):
    monkeypatch.setattr(
        "app.main.discover", lambda: [("001_a.sql", "aaa"), ("002_b.sql", "bbb")]
    )
    with pytest.raises(RuntimeError) as exc:
        verify_schema({"001_a.sql": "aaa"})
    assert "002_b.sql" in str(exc.value)


def test_refuses_on_edited_migration(monkeypatch):
    monkeypatch.setattr("app.main.discover", lambda: [("001_a.sql", "NEW")])
    with pytest.raises(RuntimeError) as exc:
        verify_schema({"001_a.sql": "OLD"})
    assert "001_a.sql" in str(exc.value)


def test_serves_when_database_is_ahead(monkeypatch):
    # A newer release migrated this database. Refusing would make rolling the
    # application back impossible, so this must serve.
    monkeypatch.setattr("app.main.discover", lambda: [("001_a.sql", "aaa")])
    verify_schema({"001_a.sql": "aaa", "002_future.sql": "zzz"})  # must not raise


def test_error_names_every_missing_migration(monkeypatch):
    monkeypatch.setattr(
        "app.main.discover",
        lambda: [("001_a.sql", "a"), ("002_b.sql", "b"), ("003_c.sql", "c")],
    )
    with pytest.raises(RuntimeError) as exc:
        verify_schema({"001_a.sql": "a"})
    message = str(exc.value)
    assert "002_b.sql" in message and "003_c.sql" in message


class _RaisingSession:
    """Fakes just enough of the async-session context-manager protocol for
    _read_ledger to reach session.execute(), which raises the given
    exception."""

    def __init__(self, to_raise):
        self._to_raise = to_raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, *args, **kwargs):
        raise self._to_raise


def _programming_error_wrapping(asyncpg_exc):
    """Reproduce the exact shape SQLAlchemy's asyncpg dialect raises: a
    ProgrammingError whose .orig is the DBAPI-layer wrapper, and whose
    .orig.__cause__ is the original asyncpg exception (confirmed empirically
    against the real driver -- see the fix report)."""
    dbapi_error = RuntimeError("driver-level error")
    dbapi_error.__cause__ = asyncpg_exc
    return ProgrammingError("SELECT filename, checksum FROM schema_migrations", {}, dbapi_error)


@pytest.mark.asyncio
async def test_read_ledger_reraises_non_missing_table_errors(monkeypatch):
    # A permission problem (or any other member of asyncpg's
    # SyntaxOrAccessError family besides UndefinedTableError) must surface
    # as itself -- not be swallowed and reported to the operator as
    # "nothing applied", which would send them to run migrations when the
    # real fault is access or a mangled ledger table.
    exc = _programming_error_wrapping(
        asyncpg.exceptions.InsufficientPrivilegeError(
            'permission denied for table "schema_migrations"'
        )
    )
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: _RaisingSession(exc))

    with pytest.raises(ProgrammingError):
        await _read_ledger()
