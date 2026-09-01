"""
Test fixtures for pytest.
"""
import sys
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create a stable session-scoped event loop for the test session.

    On Windows, aiomysql (pymysql) misbehaves under the default
    ProactorEventLoop across multiple async tests — pooled connections get a
    detached transport ('NoneType' object has no attribute 'send') once a
    connection is recycled/pre-pinged between tests. Forcing the
    SelectorEventLoop policy keeps a single, consistent loop for the whole
    session and avoids that corruption. Linux production uses SelectorEventLoop
    already, so this only affects the local test runner.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True, scope="function")
async def _reset_db_engine():
    """Dispose the SQLAlchemy engine pool after each test.

    On Windows, aiomysql connections used through httpx ASGITransport can be
    returned to the pool with a detached transport once the test's client is
    closed. The next test that checks out that connection then fails with
    AttributeError: 'NoneType' object has no attribute 'send' during pool
    pre-ping/terminate. Disposing the pool per test guarantees every test opens
    a fresh, healthy connection on the (session-scoped) loop. Production is
    unaffected — this only governs the test session.
    """
    yield
    from app.core.database import engine

    try:
        await engine.dispose()
    except Exception:
        pass


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for testing."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
    monkeypatch.setenv("INIT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "test")
    monkeypatch.setenv("MYSQL_PASSWORD", "test")
    monkeypatch.setenv("MYSQL_DATABASE", "test_db")
