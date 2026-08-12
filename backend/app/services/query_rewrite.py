"""
Query Rewrite Service - LLM-based query rewriting and expansion.
Uses LLM to rewrite user queries for better retrieval results.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from app.clients.http_client import http_client_context

from app.core.config import settings

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """你是一个查询改写专家。你的任务是将用户的原始查询改写成更适合知识库检索的形式。

规则：
1. 提取查询的核心意图，去掉具体型号、品牌等细节
2. 将具体问题改写为更通用的形式
3. 如果用户查询包含产品型号（如"SoundFree X1"、"S3 Pro"），改写时去掉型号，保留核心功能问题
4. 生成2-3个不同表述的查询变体，提高召回率
5. 保持查询的语义不变

示例：
- "SoundFree X1耳机防水吗？" → "耳机防水性能如何？"、"耳机防水等级"、"运动耳机防水"
- "S3 Pro智能手表续航时间是多少？" → "智能手表电池续航"、"手表续航能力"、"电池使用时间"

原始查询：{query}

请生成改写后的查询（JSON格式）：
{{
  "rewritten_query": "改写后的通用查询",
  "query_variants": ["变体1", "变体2", "变体3"],
  "analysis": "改写说明"
}}"""


async def rewrite_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Rewrite user query using LLM for better retrieval.

    Args:
        query: Original user query
        conversation_history: Previous conversation messages for context

    Returns:
        Dict with rewritten_query, query_variants, and analysis
    """
    # Build context from conversation history
    history_context = ""
    if conversation_history:
        recent = conversation_history[-3:]  # Last 3 messages
        history_context = "\n".join([f"用户: {m.get('question', '')}" for m in recent])

    prompt = REWRITE_PROMPT.format(query=query)
    if history_context:
        prompt = f"对话上下文：\n{history_context}\n\n{prompt}"

    try:
        async with http_client_context() as client:
            response = await client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一个JSON格式输出专家，只输出JSON，不要其他内容。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content)

            # Validate and return
            return {
                "rewritten_query": result.get("rewritten_query", query),
                "query_variants": result.get("query_variants", []),
                "analysis": result.get("analysis", ""),
                "original_query": query,
            }

    except Exception as e:
        logger.warning(f"Query rewrite failed: {e}")
        # Fallback: return original query
        return {
            "rewritten_query": query,
            "query_variants": [],
            "analysis": "查询改写失败，使用原始查询",
            "original_query": query,
        }


async def expand_query_for_search(
    query: str,
    max_variants: int = 2,
) -> list[str]:
    """
    Generate query variants for multi-query retrieval.

    Args:
        query: Original user query
        max_variants: Maximum number of variants to generate

    Returns:
        List of query variants including original
    """
    result = await rewrite_query(query)

    # Combine original + variants
    queries = [result["rewritten_query"]]
    for variant in result.get("query_variants", [])[:max_variants]:
        if variant and variant not in queries:
            queries.append(variant)

    return queries
