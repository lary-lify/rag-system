"""
Tests for documents endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_documents_without_auth(client: AsyncClient):
    """Test list documents without auth returns 401."""
    response = await client.get("/api/documents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_document_without_auth(client: AsyncClient):
    """Test upload document without auth returns 401."""
    response = await client.post("/api/documents/upload?kb_id=1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_document_without_auth(client: AsyncClient):
    """Test get document without auth returns 401."""
    response = await client.get("/api/documents/1")
    assert response.status_code == 401
