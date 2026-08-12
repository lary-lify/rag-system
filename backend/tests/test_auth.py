"""
Tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_missing_credentials(client: AsyncClient):
    """Test login with missing credentials returns 422."""
    response = await client.post("/api/auth/login", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials returns 401."""
    response = await client.post("/api/auth/login", json={
        "username": "nonexistent",
        "password": "wrongpassword"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_without_token(client: AsyncClient):
    """Test get current user without token returns 401."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_without_token(client: AsyncClient):
    """Test change password without token returns 401."""
    response = await client.post("/api/auth/change-password", json={
        "old_password": "old",
        "new_password": "new"
    })
    assert response.status_code == 401
