"""
AI-Assisted Semantic Chunking - uses LLM (DeepSeek) to detect natural
semantic boundaries in text for intelligent splitting.

Workflow:
1. Pre-split: rough paragraph-level split to stay within token limits
2. LLM analysis: send text batches to LLM, ask it to mark boundary positions
3. Split: splice text at LLM-identified boundaries
4. Fallback: if LLM fails, fall back to paragraph chunking
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from app.clients.http_client import sync_http_client_context

from app.core.config import settings
from app.services.chunking.base import BaseChunkingStrategy, ChunkResult

logger = logging.getLogger(__name__)

# Max chars per LLM batch (conservative, ~3K tokens for Chinese text)
MAX_BATCH_CHARS = 6000

# Max chars per final chunk
DEFAULT_MAX_CHUNK_SIZE = 2000
DEFAULT_MIN_CHUNK_SIZE = 50

# LLM system prompt for boundary detection
BOUNDARY_PROMPT = """You are a text segmentation expert. Your task is to identify natural semantic boundaries in the given text.

The text is a document that needs to be split into meaningful chunks. Each chunk should be a self-contained, semantically coherent unit.

Instructions:
1. Read the text carefully.
2. Identify logical break points where one topic/idea clearly ends and another begins.
3. Output ONLY a JSON array of integers, each representing the character index (0-based) where a split should occur.
4. Do NOT split in the middle of a sentence or paragraph.
5. Split at paragraph boundaries, topic shifts, section transitions, etc.
6. Each chunk should ideally be 300-1000 characters to be independently useful for retrieval.
7. Do NOT include any explanation, just the JSON array.

Example output format:
[356, 812, 1503, 2200, 2980]"""


class AIAssistedChunker(BaseChunkingStrategy):
    """
    AI-assisted chunking using LLM for semantic boundary detection.
    Falls back to paragraph chunking if LLM is unavailable.
    """

    name = "ai_assisted"

    def __init__(self):
        super().__init__()
        self._last_ai_usage: dict | None = None  # {input_tokens, output_tokens, estimated_cost}

    def get_last_ai_usage(self) -> dict | None:
        """Return token usage from the most recent split() call, or None if AI wasn't used."""
        usage = self._last_ai_usage
        self._last_ai_usage = None  # clear after read
        return usage

    def get_default_params(self) -> dict:
        return {
            "max_chunk_size": 2000,
            "min_chunk_size": 50,
            "enable_ai": True,
            "temperature": 0.1,
        }

    def split(self, text: str, **params) -> list[ChunkResult]:
        self._last_ai_usage = None  # reset per call
        max_size = params.get("max_chunk_size", DEFAULT_MAX_CHUNK_SIZE)
        min_size = params.get("min_chunk_size", DEFAULT_MIN_CHUNK_SIZE)
        enable_ai = params.get("enable_ai", True)
        temperature = params.get("temperature", 0.1)

        if not text or len(text.strip()) < min_size:
            return []

        # Short text: no splitting needed
        if len(text) <= max_size:
            return [ChunkResult(
                index=0,
                content=text.strip(),
                token_count=len(text) // 2,
                metadata={"strategy": "ai_assisted", "ai_used": False, "char_length": len(text)},
            )]

        # Step 1: Pre-split into manageable batches
        paragraphs = self._pre_split(text, max_size)

        if len(paragraphs) <= 1:
            # Already a single chunk
            return [ChunkResult(
                index=0,
                content=text.strip()[:max_size],
                token_count=min(len(text), max_size) // 2,
                metadata={"strategy": "ai_assisted", "ai_used": False, "char_length": min(len(text), max_size)},
            )]

        # Step 2: Use LLM to find semantic boundaries (with fallback)
        boundaries: list[int] = []
        if enable_ai and settings.DEEPSEEK_API_KEY:
            boundaries = self._detect_boundaries_with_llm(text, paragraphs, temperature)
            logger.info(f"[ai_chunking] LLM returned {len(boundaries)} boundaries for {len(text)} chars")
        else:
            logger.info("[ai_chunking] AI disabled or no API key, using paragraph boundaries")

        # Step 3: Apply boundaries to split text
        chunks = self._apply_boundaries(text, boundaries, max_size, min_size)

        # Assign metadata
        results = []
        for i, chunk_content in enumerate(chunks):
            content = chunk_content.strip()
            if len(content) < min_size:
                continue
            results.append(ChunkResult(
                index=i,
                content=content,
                token_count=len(content) // 2,
                metadata={
                    "strategy": "ai_assisted",
                    "ai_used": len(boundaries) > 0,
                    "char_length": len(content),
                    "boundary_count": len(boundaries),
                },
            ))

        return results if results else [ChunkResult(
            index=0,
            content=text.strip()[:max_size],
            token_count=max_size // 2,
            metadata={"strategy": "ai_assisted", "ai_used": False, "char_length": max_size},
        )]

    def _pre_split(self, text: str, max_chunk_size: int) -> list[str]:
        """
        Coarse split into paragraph groups, each under max_chunk_size.
        This is a rough pass — LLM will refine boundaries later.
        """
        lines = text.split("\n")
        groups: list[str] = []
        current_group = ""

        for line in lines:
            candidate = current_group + ("\n" if current_group else "") + line

            if len(candidate) > max_chunk_size and current_group:
                groups.append(current_group.strip())
                current_group = line
            else:
                current_group = candidate

        if current_group.strip():
            groups.append(current_group.strip())

        # If no good split found, fallback to raw chunks
        if not groups:
            groups = [text]

        return groups

    def _detect_boundaries_with_llm(
        self, text: str, paragraphs: list[str], temperature: float
    ) -> list[int]:
        """
        Send text to LLM and get semantic boundary positions.
        Returns list of character indices where splits should occur.
        """
        # Build context with annotated positions
        annotated = self._annotate_text(text, paragraphs)

        messages = [
            {"role": "system", "content": BOUNDARY_PROMPT},
            {"role": "user", "content": f"""Here is the text to segment. Pay attention to topic shifts and semantic boundaries.

{annotated}

Return ONLY the JSON array of boundary character indices (0-based)."""},
        ]

        try:
            with sync_http_client_context() as client:
                response = client.post(
                    f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.DEEPSEEK_CHAT_MODEL,
                        "messages": messages,
                        "stream": False,
                        "temperature": temperature,
                    "max_tokens": 1024,
                },
                timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Record token usage from API response
                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                if input_tokens or output_tokens:
                    cost = round(
                        input_tokens * settings.DEEPSEEK_INPUT_TOKEN_PRICE
                        + output_tokens * settings.DEEPSEEK_OUTPUT_TOKEN_PRICE,
                        6,
                    )
                    self._last_ai_usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "estimated_cost": cost,
                    }
                    logger.info(
                        f"[ai_chunking] LLM tokens: {input_tokens} in + {output_tokens} out, cost=¥{cost:.6f}"
                    )

                # Extract JSON array from response
                boundaries = self._parse_boundary_response(content)
                return self._clean_boundaries(boundaries, len(text))

        except httpx.HTTPStatusError as e:
            logger.warning(f"[ai_chunking] LLM HTTP error: {e.response.status_code}, falling back to paragraph")
            return []
        except Exception as e:
            logger.warning(f"[ai_chunking] LLM call failed: {e}, falling back to paragraph")
            return []

    def _annotate_text(self, text: str, paragraphs: list[str]) -> str:
        """Annotate text with paragraph markers for LLM context."""
        result_parts = []
        pos = 0
        for i, para in enumerate(paragraphs):
            start = text.find(para, pos)
            if start == -1:
                start = pos
            end = start + len(para)
            preview = para[:80].replace("\n", " ").strip()
            result_parts.append(
                f"[Paragraph {i} | chars {start}-{end}] {preview}..."
                if len(para) > 80
                else f"[Paragraph {i} | chars {start}-{end}] {preview}"
            )
            pos = end

        return "\n".join(result_parts)

    def _parse_boundary_response(self, content: str) -> list[int]:
        """Extract boundary indices from LLM response."""
        # Try direct JSON parse
        try:
            result = json.loads(content)
            if isinstance(result, list):
                return [int(x) for x in result]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Try to extract JSON array from mixed content (with markdown wrapping)
        json_match = re.search(r"\[[\d,\s]+\]", content)
        if json_match:
            try:
                return [int(x.strip()) for x in json_match.group(0).strip("[]").split(",") if x.strip()]
            except (ValueError, TypeError):
                pass

        # Try to extract all numbers from response
        numbers = re.findall(r"\b(\d+)\b", content)
        if numbers:
            return [int(n) for n in numbers if 0 < int(n) < 100000]

        return []

    def _clean_boundaries(self, boundaries: list[int], text_length: int) -> list[int]:
        """Remove invalid boundaries (out of range, too close, duplicates)."""
        cleaned = sorted(set(b for b in boundaries if 0 < b < text_length))
        # Remove boundaries that are too close together (min 100 chars apart)
        min_gap = 100
        if not cleaned:
            return []
        result = [cleaned[0]]
        for b in cleaned[1:]:
            if b - result[-1] >= min_gap:
                result.append(b)
        return result

    def _apply_boundaries(
        self,
        text: str,
        boundaries: list[int],
        max_size: int,
        min_size: int,
    ) -> list[str]:
        """Split text at given boundary positions."""
        if not boundaries:
            # Fallback: split by paragraph boundaries
            return self._split_by_paragraphs(text, max_size, min_size)

        chunks: list[str] = []
        prev = 0
        for boundary in sorted(boundaries):
            chunk = text[prev:boundary].strip()
            if len(chunk) >= min_size:
                if len(chunk) > max_size:
                    # Sub-split oversized chunk
                    sub_chunks = self._split_by_paragraphs(chunk, max_size, min_size)
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(chunk)
            prev = boundary

        # Add trailing content
        tail = text[prev:].strip()
        if len(tail) >= min_size:
            if len(tail) > max_size:
                sub_chunks = self._split_by_paragraphs(tail, max_size, min_size)
                chunks.extend(sub_chunks)
            else:
                chunks.append(tail)
        elif tail and chunks:
            # Merge small tail into last chunk (if it fits)
            merged = chunks[-1] + "\n" + tail
            if len(merged) <= max_size:
                chunks[-1] = merged
            # else discard small tail

        return chunks

    def _split_by_paragraphs(self, text: str, max_size: int, min_size: int) -> list[str]:
        """Fallback: split by paragraph boundaries."""
        chunks: list[str] = []
        current = ""
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                if current and len(current) >= min_size:
                    chunks.append(current)
                    current = ""
                continue

            test = current + ("\n" if current else "") + line
            if len(test) > max_size and current:
                chunks.append(current)
                current = line
            else:
                current = test

        if current.strip() and len(current.strip()) >= min_size:
            chunks.append(current.strip())
        elif current.strip() and chunks:
            # Merge small tail
            chunks[-1] = chunks[-1] + "\n" + current.strip()

        return chunks if chunks else [text[:max_size].strip()]
