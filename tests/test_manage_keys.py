"""scripts/manage_keys.py's set-limit subcommand.

scripts/manage_keys.py is a standalone script, not a package under app/, so it
is loaded here the same way `python scripts/manage_keys.py` would load it: by
putting scripts/ on sys.path and importing it as a top-level module.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest  # noqa: E402

import manage_keys  # noqa: E402


def test_set_limit_subcommand_dispatches_to_set_limit():
    parser = manage_keys.build_parser()
    args = parser.parse_args(["set-limit", "--prefix", "lxr_kJ8mN2pQ", "--limit", "5000"])
    assert args.fn is manage_keys.set_limit
    assert args.prefix == "lxr_kJ8mN2pQ"
    assert args.limit == 5000


def test_set_limit_requires_both_arguments():
    parser = manage_keys.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["set-limit", "--prefix", "lxr_kJ8mN2pQ"])


def test_validate_limit_rejects_zero_and_negative():
    # A zero limit silently bricks a key rather than revoking it, which is a
    # different operation with its own subcommand. Refuse it loudly instead.
    for bad in (0, -1, -1000):
        with pytest.raises(SystemExit):
            manage_keys._validate_limit(bad)


def test_validate_limit_accepts_positive():
    assert manage_keys._validate_limit(5000) == 5000


def test_existing_subcommands_still_dispatch():
    # build_parser() is an extraction from main(); prove it did not drop anything.
    parser = manage_keys.build_parser()
    assert parser.parse_args(["list"]).fn is manage_keys.list_keys
    assert parser.parse_args(["revoke", "--prefix", "lxr_x"]).fn is manage_keys.revoke
    issued = parser.parse_args(["issue", "--email", "a@b.c"])
    assert issued.fn is manage_keys.issue
    assert issued.daily_limit == 1000
