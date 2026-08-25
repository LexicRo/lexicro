import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limit import check_rate_limit


@pytest.fixture(scope="session")
def client():
    """A single, context-managed TestClient shared by the whole session.

    Entering TestClient(app) as a context manager keeps one event loop alive
    for every request, instead of a fresh one per request (which kills a
    connection pool opened on an earlier, now-closed loop after the first
    DB-touching call).

    Also stubs check_rate_limit for the whole suite: it queries Postgres on
    every rate-limited route and enforces a real, wall-clock-day-scoped daily
    quota there. No test in this suite asserts on rate-limiting behaviour, so
    nothing is lost, and without the override the suite's pass/fail outcome
    would depend on how many times it had already been run today.
    """
    app.dependency_overrides[check_rate_limit] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(check_rate_limit, None)
