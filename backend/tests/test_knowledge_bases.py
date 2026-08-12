"""
Tests for knowledge bases endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_knowledge_bases_without_auth(client: AsyncClient):
    """Test list knowledge bases without auth returns 401."""
    response = await client.get("/api/knowledge-bases")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_knowledge_base_without_auth(client: AsyncClient):
    """Test create knowledge base without auth returns 401."""
    response = await client.post("/api/knowledge-bases", json={
        "name": "Test KB",
        "description": "Test description"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_knowledge_base_without_auth(client: AsyncClient):
    """Test get knowledge base without auth returns 401."""
    response = await client.get("/api/knowledge-bases/1")
    assert response.status_code == 401
