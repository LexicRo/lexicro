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

    Also stubs out check_rate_limit for the whole suite. That name undersells
    what it disables: check_rate_limit is not only the daily-quota check, it
    is the API-key AUTHENTICATION path -- every 401 an invalid, revoked or
    inactive key produces anywhere in the app -- and it performs the
    request_log usage-metering INSERT on every rate-limited route. This
    override replaces it with a no-op, so no test built on this fixture can
    exercise authentication (a test asserting a 401 would pass vacuously,
    never having reached the real check) and no request against this client
    is metered. Without the override, the suite's pass/fail outcome would
    also depend on how many times it had already been run today, since the
    quota is a real, wall-clock-day-scoped count against Postgres.

    A test file that needs to exercise authentication (a real 401, or a real
    request_log write) must remove this override -- e.g. via
    `app.dependency_overrides.pop(check_rate_limit, None)` in its own setup,
    or by not depending on this fixture -- rather than relying on it.
    """
    app.dependency_overrides[check_rate_limit] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(check_rate_limit, None)
