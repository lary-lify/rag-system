"""
Semantic Chunking - split by semantic similarity using sliding window.
Groups semantically similar sentences together.
"""
from __future__ import annotations

import math
import re

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


class SemanticChunker(BaseChunkingStrategy):
    """Split text by detecting semantic boundaries between paragraphs/sentences."""

    name = "semantic"

    def get_default_params(self) -> dict:
        return {
            "max_chunk_size": 1024,
            "min_chunk_size": 100,
            "similarity_threshold": 0.5,
            "sentence_split_pattern": r'(?<=[。！？.!?])\s*(?=[^。！？.!?\n]|$)',
        }

    def _split_sentences(self, text: str, pattern: str) -> list[str]:
        """Split text into sentences."""
        if not pattern:
            return [text]
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, a: dict[str, int], b: dict[str, int]) -> float:
        """Simple word-overlap cosine similarity for sentence boundary detection."""
        if not a or not b:
            return 0.0
        common = sum(min(a.get(k, 0), b.get(k, 0)) for k in set(a.keys()) & set(b.keys()))
        mag_a = math.sqrt(sum(v * v for v in a.values())) or 1
        mag_b = math.sqrt(sum(v * v for v in b.values())) or 1
        return common / (mag_a * mag_b)

    def _word_freq(self, text: str) -> dict[str, int]:
        """Simple character/word frequency vector (Chinese-friendly)."""
        freq: dict[str, int] = {}
        # For Chinese, use bigram; for English, use words
        chars = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+', text)
        for c in chars:
            freq[c] = freq.get(c, 0) + 1
        return freq

    def split(self, text: str, **params) -> list[ChunkResult]:
        max_size = params.get("max_chunk_size", 1024)
        min_size = params.get("min_chunk_size", 100)
        threshold = params.get("similarity_threshold", 0.5)
        pattern = params.get("sentence_split_pattern", "")

        sentences = self._split_sentences(text, pattern)
        if len(sentences) <= 1:
            return [ChunkResult(index=0, content=text, token_count=len(text) // 2)]

        chunks: list[ChunkResult] = []
        current_group: list[str] = []
        current_len = 0
        prev_vec: dict[str, int] | None = None
        idx = 0

        for sent in sentences:
            sent_len = len(sent)
            vec = self._word_freq(sent)

            # Check if this sentence is a semantic break point
            should_break = False
            if prev_vec and current_len >= min_size:
                sim = self._cosine_similarity(prev_vec, vec)
                if sim < threshold:
                    should_break = True
            elif current_len + sent_len > max_size:
                should_break = True

            if should_break and current_group:
                content = "".join(current_group).strip()
                chunks.append(ChunkResult(
                    index=idx,
                    content=content,
                    token_count=len(content) // 2,
                    metadata={"sentence_count": len(current_group)},
                ))
                idx += 1
                current_group = []
                current_len = 0

            current_group.append(sent)
            current_len += sent_len
            prev_vec = vec

        # Flush remaining
        if current_group:
            content = "".join(current_group).strip()
            chunks.append(ChunkResult(
                index=idx,
                content=content,
                token_count=len(content) // 2,
                metadata={"sentence_count": len(current_group)},
            ))

        return chunks
