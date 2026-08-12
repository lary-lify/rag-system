"""
Tests for rate limiting.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_no_rate_limit(client: AsyncClient):
    """Test health check is not rate limited."""
    # Health check should not be rate limited
    for _ in range(15):
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_rate_limit(client: AsyncClient):
    """Test login endpoint has rate limiting."""
    # Make multiple login attempts
    for i in range(12):
        response = await client.post("/api/auth/login", json={
            "username": "test",
            "password": "test"
        })
        # First 10 should work (401 for wrong creds), then rate limited (429)
        if i >= 10:
            assert response.status_code == 429
        else:
            assert response.status_code in [401, 429]
