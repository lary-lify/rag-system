"""
Paragraph Chunking - split by paragraph boundaries (double newlines).
Best for structured documents with clear paragraphs.
"""
from __future__ import annotations

import re

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


class ParagraphChunker(BaseChunkingStrategy):
    """Split text at paragraph (double newline) boundaries."""

    name = "paragraph"

    def get_default_params(self) -> dict:
        return {
            "max_paragraph_size": 2048,
            "merge_small": True,
            "merge_threshold": 200,
        }

    def split(self, text: str, **params) -> list[ChunkResult]:
        max_size = params.get("max_paragraph_size", 2048)
        merge_small = params.get("merge_small", True)
        merge_threshold = params.get("merge_threshold", 200)

        # Split by double newlines (or more)
        raw_paras = re.split(r'\n\s*\n', text)
        raw_paras = [p.strip() for p in raw_paras if p.strip()]

        if not raw_paras:
            return [ChunkResult(index=0, content=text, token_count=len(text) // 2)]

        chunks: list[ChunkResult] = []
        idx = 0
        buffer: list[str] = []
        buffer_len = 0

        for para in raw_paras:
            para_len = len(para)
            if buffer_len + para_len > max_size and buffer:
                # Flush buffer
                content = "\n\n".join(buffer).strip()
                if content:
                    chunks.append(ChunkResult(
                        index=idx,
                        content=content,
                        token_count=len(content) // 2,
                        metadata={"paragraph_count": len(buffer)},
                    ))
                    idx += 1
                buffer = []
                buffer_len = 0

            # Merge small paragraphs into previous chunk?
            if merge_small and para_len < merge_threshold and buffer:
                buffer.append(para)
                buffer_len += para_len
                continue

            buffer.append(para)
            buffer_len += para_len

        # Flush remaining
        if buffer:
            content = "\n\n".join(buffer).strip()
            if content:
                chunks.append(ChunkResult(
                    index=idx,
                    content=content,
                    token_count=len(content) // 2,
                    metadata={"paragraph_count": len(buffer)},
                ))

        return chunks
