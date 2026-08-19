"""Which migrations does this image ship, and which has the database had?

Pure logic, deliberately free of database access, so it can be unit-tested
without Postgres AND so the CLI runner and the application's startup gate
reach their verdicts through the same code path rather than two similar ones.

See ADR-0023.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# app/schema_state.py -> app/ -> repo root -> migrations/
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def normalise(raw: bytes) -> bytes:
    """CRLF -> LF.

    This repo has no .gitattributes and core.autocrlf rewrites line endings on
    checkout, so the Windows working tree differs byte-for-byte from the Linux
    checkout the image is built from. Hashing raw bytes would report a fatal
    checksum mismatch for a file nobody touched.
    """
    return raw.replace(b"\r\n", b"\n")


def checksum(raw: bytes) -> str:
    """sha256 of the normalised bytes, as hex."""
    return hashlib.sha256(normalise(raw)).hexdigest()


def discover(directory: Path | None = None) -> list[tuple[str, str]]:
    """[(filename, checksum)] for every .sql file, sorted by filename.

    Filename order IS application order -- the numeric prefix is the contract.
    """
    directory = MIGRATIONS_DIR if directory is None else directory
    return [
        (p.name, checksum(p.read_bytes()))
        for p in sorted(directory.glob("*.sql"), key=lambda p: p.name)
    ]


@dataclass
class SchemaState:
    pending: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    ahead: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Safe to serve. `ahead` is deliberately not disqualifying: the
        database was migrated by a newer release, and refusing would make
        rolling the application back impossible."""
        return not self.pending and not self.mismatched


def diff(files: list[tuple[str, str]], applied: dict[str, str]) -> SchemaState:
    """Compare shipped migration files against ledger rows.

    `applied` maps filename -> checksum recorded when it was applied.
    """
    state = SchemaState()
    shipped = {name for name, _ in files}

    for name, digest in files:
        if name not in applied:
            state.pending.append(name)
        elif applied[name] != digest:
            state.mismatched.append(name)

    state.ahead = sorted(name for name in applied if name not in shipped)
    return state
