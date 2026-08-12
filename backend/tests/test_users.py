"""
Tests for users endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_users_without_auth(client: AsyncClient):
    """Test list users without auth returns 401."""
    response = await client.get("/api/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_without_auth(client: AsyncClient):
    """Test get user without auth returns 401."""
    response = await client.get("/api/users/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_without_auth(client: AsyncClient):
    """Test update user without auth returns 401."""
    response = await client.put("/api/users/1", json={
        "real_name": "Test"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_user_without_auth(client: AsyncClient):
    """Test delete user without auth returns 401."""
    response = await client.delete("/api/users/1")
    assert response.status_code == 401
