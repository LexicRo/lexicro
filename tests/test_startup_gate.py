"""The startup gate refuses to serve a database it does not recognise (ADR-0023)."""

import pytest

from app.main import verify_schema


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
