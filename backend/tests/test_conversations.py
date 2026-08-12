"""
Tests for conversations endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_conversations_without_auth(client: AsyncClient):
    """Test list conversations without auth returns 401."""
    response = await client.get("/api/conversations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_conversation_without_auth(client: AsyncClient):
    """Test create conversation without auth returns 401."""
    response = await client.post("/api/conversations", json={
        "title": "Test Conversation"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_without_auth(client: AsyncClient):
    """Test chat without auth returns 401."""
    response = await client.post("/api/conversations/chat", json={
        "question": "Hello"
    })
    assert response.status_code == 401
