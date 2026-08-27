"""Contract tests for /health.

/health is the only thing the production monitoring reads. `probe_api.sh`
runs every 10 minutes and pings a healthchecks.io dead-man's switch ONLY on
a 2xx (`curl -f`), so the status code this endpoint chooses is what decides
whether a failure wakes anyone. The body is for the human who then looks.

Until 0.6.1 the endpoint touched no database and would have returned 200
throughout a total database outage -- the gap recorded as OQ-022 part 3.
"""

import asyncio

import pytest

import app.main
from app.database import database_ok


def test_health_reports_the_database_when_it_is_reachable(client, monkeypatch):
    monkeypatch.setattr(app.main, "database_ok", _fake(True))
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_health_returns_503_when_the_database_is_unreachable(client, monkeypatch):
    """The status code is the alert. A 200 here is the OQ-022 defect.

    probe_api.sh pings the dead-man's switch only on a 2xx, so returning 200
    with a sad-looking body would leave the check green through a database
    outage and change nothing about what the monitoring catches.
    """
    monkeypatch.setattr(app.main, "database_ok", _fake(False))
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unreachable"


def test_both_health_bodies_carry_the_same_keys(client, monkeypatch):
    """A monitor should not need two parsers for one endpoint.

    In particular `version` survives degradation: knowing WHICH build is
    failing is most of the value of asking during an incident.
    """
    monkeypatch.setattr(app.main, "database_ok", _fake(True))
    healthy = client.get("/health").json()
    monkeypatch.setattr(app.main, "database_ok", _fake(False))
    degraded = client.get("/health").json()

    assert set(healthy) == set(degraded)
    assert healthy["version"] == degraded["version"]


def test_database_ok_returns_false_rather_than_raising(monkeypatch):
    """/health must answer even when the database is the thing that is broken.

    An exception escaping here would surface as a 500 from the framework,
    with no body and no version -- strictly less useful than the 503 this
    endpoint is meant to serve.
    """
    class Boom:
        def __call__(self):
            raise OSError("connection refused")

    monkeypatch.setattr("app.database.AsyncSessionLocal", Boom())
    assert asyncio.run(database_ok()) is False


def test_database_ok_is_bounded_when_the_database_hangs(monkeypatch):
    """A hung database must not become a hung health endpoint.

    Without a timeout this is worse than the defect it replaces: the probe's
    own `-m 15` would eventually fire, but the container healthcheck and any
    human curl would sit there, and a health endpoint that hangs is a health
    endpoint that lies by omission.
    """
    class Hang:
        def __call__(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *a, **kw):
            await asyncio.sleep(30)

    monkeypatch.setattr("app.database.AsyncSessionLocal", Hang())

    async def run():
        started = asyncio.get_running_loop().time()
        result = await database_ok(timeout=0.25)
        return result, asyncio.get_running_loop().time() - started

    result, elapsed = asyncio.run(run())
    assert result is False
    assert elapsed < 5, "database_ok did not honour its timeout"


def _fake(value):
    async def _database_ok(*args, **kwargs):
        return value
    return _database_ok
