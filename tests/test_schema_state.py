"""Pure schema-state logic (ADR-0023). No database, no filesystem beyond tmp_path."""

from app.schema_state import SchemaState, checksum, diff, discover, normalise


def test_normalise_converts_crlf_to_lf():
    assert normalise(b"a\r\nb\r\n") == b"a\nb\n"


def test_normalise_leaves_lf_alone():
    assert normalise(b"a\nb\n") == b"a\nb\n"


def test_checksum_is_line_ending_agnostic():
    # The whole point: a Windows checkout and a Linux checkout of the same
    # migration must produce the same checksum, or the startup gate fires
    # fatally on a file nobody edited.
    assert checksum(b"SELECT 1;\r\n") == checksum(b"SELECT 1;\n")


def test_checksum_differs_on_real_change():
    assert checksum(b"SELECT 1;\n") != checksum(b"SELECT 2;\n")


def test_discover_returns_sorted_filename_checksum_pairs(tmp_path):
    (tmp_path / "002_b.sql").write_bytes(b"SELECT 2;\n")
    (tmp_path / "001_a.sql").write_bytes(b"SELECT 1;\n")
    found = discover(tmp_path)
    assert [f for f, _ in found] == ["001_a.sql", "002_b.sql"]
    assert found[0][1] == checksum(b"SELECT 1;\n")


def test_discover_ignores_non_sql_files(tmp_path):
    (tmp_path / "001_a.sql").write_bytes(b"SELECT 1;\n")
    (tmp_path / "README.md").write_bytes(b"not a migration\n")
    assert [f for f, _ in discover(tmp_path)] == ["001_a.sql"]


def test_diff_all_pending_when_ledger_empty():
    files = [("001_a.sql", "aaa"), ("002_b.sql", "bbb")]
    state = diff(files, {})
    assert state.pending == ["001_a.sql", "002_b.sql"]
    assert state.mismatched == []
    assert state.ahead == []
    assert state.ok is False


def test_diff_ok_when_everything_applied():
    files = [("001_a.sql", "aaa")]
    state = diff(files, {"001_a.sql": "aaa"})
    assert state.pending == []
    assert state.ok is True


def test_diff_detects_edited_migration():
    files = [("001_a.sql", "NEW")]
    state = diff(files, {"001_a.sql": "OLD"})
    assert state.mismatched == ["001_a.sql"]
    assert state.pending == []
    assert state.ok is False


def test_diff_detects_ahead_database():
    # The ledger knows a migration this image does not ship: the database was
    # migrated by a newer release. Not an error -- rollback must stay possible.
    files = [("001_a.sql", "aaa")]
    state = diff(files, {"001_a.sql": "aaa", "002_future.sql": "zzz"})
    assert state.ahead == ["002_future.sql"]
    assert state.pending == []
    assert state.ok is True


def test_diff_pending_preserves_file_order():
    files = [("001_a.sql", "a"), ("002_b.sql", "b"), ("003_c.sql", "c")]
    state = diff(files, {"001_a.sql": "a"})
    assert state.pending == ["002_b.sql", "003_c.sql"]
