"""
Tests for health check endpoint.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data


@pytest.mark.asyncio
async def test_health_check_returns_json(client: AsyncClient):
    """Test health check returns valid JSON."""
    response = await client.get("/api/health")
    assert response.headers["content-type"] == "application/json"
