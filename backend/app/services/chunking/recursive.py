"""
Recursive Text Chunking - hierarchical splitting with configurable separators.
Uses a tree-like structure: splits by large separators first, then
recursively splits each chunk if it's still too large. Preserves context
by keeping separator text with each chunk.
"""
from __future__ import annotations

from typing import Any

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


class RecursiveChunker(BaseChunkingStrategy):
    """
    Recursive chunking strategy.
    Splits by a hierarchy of separators (paragraph -> sentence -> fixed-size),
    recursively splitting any chunk that exceeds max_size until it fits.
    """

    name = "recursive"

    # Separator hierarchy (ordered from coarse to fine)
    DEFAULT_SEPARATORS = [
        ("\n\n", "double_newline", 2),      # Paragraph boundary
        ("\n", "newline", 1),               # Line break
        ("。", "period_zh", 0.8),            # Chinese period
        (". ", "period_en", 0.5),            # English period + space
        ("; ", "semicolon", 0.5),             # Semicolon
        (", ", "comma", 0.3),                # Comma
    ]

    def get_default_params(self) -> dict:
        return {
            "max_chunk_size": 512,
            "min_chunk_size": 50,
            "overlap_sentences": 1,
            "use_sentence_boundary": True,
        }

    def split(self, text: str, **params) -> list[ChunkResult]:
        max_size = params.get("max_chunk_size", 512)
        min_size = params.get("min_chunk_size", 50)
        overlap_sents = params.get("overlap_sentences", 1)

        if not text or len(text) <= max_size:
            return [ChunkResult(index=0, content=text.strip(), token_count=len(text) // 2)]

        chunks = self._recursive_split(
            text,
            self.DEFAULT_SEPARATORS,
            level=0,
            max_size=max_size,
            min_size=min_size,
            overlap_sents=overlap_sents,
        )

        # Assign indices and metadata
        results = []
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) >= min_size:
                results.append(ChunkResult(
                    index=i,
                    content=chunk.strip(),
                    token_count=len(chunk) // 2,
                    metadata={
                        "strategy": "recursive",
                        "split_level": 0,
                        "char_length": len(chunk),
                    },
                ))

        return results if results else [ChunkResult(index=0, content=text[:max_size], token_count=max_size // 2)]

    def _recursive_split(
        self,
        text: str,
        separators: list,
        level: int,
        max_size: int,
        min_size: int,
        overlap_sents: int,
    ) -> list[str]:
        """Recursively split text using separator hierarchy."""
        if len(text) <= max_size:
            return [text]

        # Find the best separator at this level
        sep_char, sep_name, sep_weight = separators[level % len(separators)]
        parts = text.split(sep_char)

        if len(parts) <= 1:
            # Separator not found or only one part - try next level separator
            if level + 1 < len(separators):
                return self._recursive_split(text, separators, level + 1, max_size, min_size, overlap_sents)
            else:
                # Last resort: force split at max_size
                return self._force_split(text, max_size)

        result_chunks: list[str] = []
        current_chunk = ""

        for i, part in enumerate(parts):
            test_content = current_chunk + (sep_char if current_chunk else "") + part

            if len(test_content) <= max_size:
                current_chunk = test_content
            else:
                # Current chunk would exceed max size
                if current_chunk and len(current_chunk.strip()) >= min_size:
                    result_chunks.append(current_chunk)
                elif current_chunk:
                    # Current chunk is small, merge anyway but trim
                    result_chunks.append(current_chunk[:max_size])

                # Start new chunk with overlap (include last N sentences)
                if overlap_sents > 0 and sep_char in ["\n\n", "\n"]:
                    prev_parts = parts[max(0, i - overlap_sents):i]
                    current_chunk = sep_char.join(prev_parts)
                else:
                    current_chunk = part

        # Don't forget the last accumulated chunk
        if current_chunk and len(current_chunk.strip()) >= min_size:
            result_chunks.append(current_chunk)
        elif current_chunk:
            result_chunks[-1] = result_chunks[-1] + current_chunk[:max_size - len(result_chunks[-1])]

        # Recursively split chunks that are still too large
        final_result = []
        for chunk in result_chunks:
            if len(chunk) > max_size and level + 1 < len(separators):
                sub_chunks = self._recursive_split(chunk, separators, level + 1, max_size, min_size, overlap_sents)
                final_result.extend(sub_chunks)
            else:
                final_result.append(chunk)

        return final_result

    def _force_split(self, text: str, max_size: int) -> list[str]:
        """Fallback: simple character-count splitting."""
        chunks = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + max_size, len(text))
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
                idx += 1
            start = end - (max_size // 4)  # 25% overlap
        return chunks if chunks else [text[:max_size]]
