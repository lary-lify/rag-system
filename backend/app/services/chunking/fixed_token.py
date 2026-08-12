"""
Fixed Token Chunking - split by fixed token/character count with overlap.
Most commonly used, works well for most document types.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


class FixedTokenChunker(BaseChunkingStrategy):
    """Split text into chunks of approximately N characters/tokens with overlap."""

    name = "fixed_token"

    def get_default_params(self) -> dict:
        return {
            "chunk_size": 512,
            "overlap": 128,
        }

    def split(self, text: str, **params) -> list[ChunkResult]:
        chunk_size = params.get("chunk_size", 512)
        overlap = params.get("overlap", 128)

        if not text or chunk_size <= 0:
            return [ChunkResult(index=0, content=text, token_count=len(text))]

        if overlap >= chunk_size:
            overlap = chunk_size // 4

        chunks: list[ChunkResult] = []
        start = 0
        text_len = len(text)
        idx = 0

        while start < text_len:
            end = min(start + chunk_size, text_len)
            # Try to find a sentence boundary near end
            if end < text_len:
                # Look for last . ! ? or newline before end
                boundary_region = text[max(start + chunk_size - 100, start):end]
                last_boundary = max(
                    boundary_region.rfind("."),
                    boundary_region.rfind("!"),
                    boundary_region.rfind("?"),
                    boundary_region.rfind("\n\n"),
                    -1,
                )
                if last_boundary >= 20:
                    end = start + chunk_size - 100 + last_boundary + 1

            content = text[start:end].strip()
            if content:
                token_estimate = len(content) // 2  # rough Chinese char ~ 2 tokens
                chunks.append(ChunkResult(
                    index=idx,
                    content=content,
                    token_count=token_estimate,
                    metadata={"start_char": start, "end_char": end},
                ))
                idx += 1

            new_start = end - overlap
            if new_start <= start:  # prevent infinite loop when overlap >= remaining
                break
            start = new_start

        return chunks
