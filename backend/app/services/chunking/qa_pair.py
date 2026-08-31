"""
QA Pair Chunking - split text by question-answer pair patterns.
Best for FAQ documents, interview transcripts, Q&A datasets.
Detects patterns like:
  - "Q:" / "A:", "问：" / "答："
  - Numbered Q/A format
  - Markdown Q/A headers
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


class QAPairChunker(BaseChunkingStrategy):
    """Split text into chunks based on Q&A pair detection."""

    name = "qa_pair"

    # Ordered list of (question_pattern, answer_pattern) tuples
    QA_PATTERNS = [
        # Chinese Q/A
        (r'^\s*(?:问题|问|Q|q)\s*[:：]\s*(.+)', r'^(?:回答|答|A|a)\s*[:：]\s*(.+)', 'zh_qa'),
        # English Q/A
        (r'^\s*[Qq]\.\s+(.+)', r'^[Aa]\.\s+(.+)', 'en_qa_dot'),
        # Bold Q/A in markdown
        (r'\*\*\s*([Qq]uestion\s*:?\s*)\*\*', r'\*\*\s*([Aa]nswer\s*:?\s*)\*\*', 'md_bold'),
        # Numbered Q/A pairs (e.g., "Q1." / "A1.")
        (r'^\s*[Qq](\d+)[.:\)]\s*(.+)', r'^\s*[Aa](\d+)[.:\)]\s*(.+)', 'numbered'),
        # Bracketed [Q] [A]
        (r'^\[Q\]\s*(.+)', r'^\[A\]\s*(.+)', 'bracket'),
        # === separator style FAQ
        (r'^(.+)\s*=+\s*$', None, 'separator'),  # question before === line is a section header
    ]

    def get_default_params(self) -> dict:
        return {
            "min_chunk_size": 20,
            "max_chunk_size": 2000,
            "include_q_prefix": True,
            "include_a_prefix": True,
        }

    def _detect_qa_pairs(self, text: str) -> list[tuple[str, str]]:
        """
        Detect Q&A pairs from text.
        Returns list of (question_text, answer_text).
        """
        lines = text.split('\n')
        pairs = []
        current_q = ""
        current_a_parts: list[str] = []
        state = "seeking_q"  # seeking_q | collecting_a

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            q_match = self._match_question(stripped)
            a_match = self._match_answer(stripped)

            if state == "seeking_q" and q_match:
                current_q = q_match
                state = "collecting_a"
            elif state == "collecting_a":
                if q_match:
                    # Save previous Q+A before starting new Q
                    if current_q:
                        pairs.append((current_q, '\n'.join(current_a_parts).strip()))
                    current_q = q_match
                    current_a_parts = []
                    # state stays as collecting_a
                elif a_match:
                    current_a_parts.append(a_match)
                    # Check if this A is complete (next Q or end)
                    # For now, accumulate until next Q found

        # Save last pending pair
        if current_q:
            pairs.append((current_q, '\n'.join(current_a_parts).strip()))

        # Filter out empty/very short entries
        return [
            (q.strip(), a.strip())
            for q, a in pairs
            if len(q.strip()) >= 3
        ]

    def _match_question(self, text: str) -> str | None:
        """Check if line looks like a question. Returns cleaned question text or None."""
        for idx, (q_pat, _, _) in enumerate(self.QA_PATTERNS):
            m = re.match(q_pat, text)
            if m:
                # R-03 修复：编号模式 `r'^\s*[Qq](\d+)[.:\)]\s*(.+)'` 有 2 个捕获组，
                # group(1)=编号、group(2)=问题全文。原代码取 group(1) 只拿到编号，
                # 导致 Q1./A1. 模式把问题写成 "Q3:1"。统一取最后一个捕获组（即问题/答案全文）。
                group_val = m.group(m.lastindex or 1).strip()
                return f"Q{idx}:{group_val}" if self._get_param("include_q_prefix", True) else group_val
        return None

    def _match_answer(self, text: str) -> str | None:
        """Check if line looks like an answer. Returns cleaned answer text or None."""
        for idx, (_, a_pat, _) in enumerate(self.QA_PATTERNS):
            if a_pat is None:
                continue
            m = re.match(a_pat, text)
            if m:
                # R-03 修复：与 _match_question 同理，取最后一个捕获组（答案全文）。
                group_val = m.group(m.lastindex or 1).strip()
                return f"A{idx}:{group_val}" if self._get_param("include_a_prefix", True) else group_val
        return None

    def _get_param(self, key: str, default):
        params = {}
        try:
            params = self._cached_params
        except AttributeError:
            pass
        return params.get(key, default)

    def split(self, text: str, **params) -> list[ChunkResult]:
        min_size = params.get("min_chunk_size", 20)
        max_size = params.get("max_chunk_size", 2000)
        include_q = params.get("include_q_prefix", True)
        include_a = params.get("include_a_prefix", True)

        # Cache params for helper methods
        self._cached_params = params

        pairs = self._detect_qa_pairs(text)

        if not pairs:
            # No QA pattern detected - fall back to paragraph splitting
            from app.services.chunking.paragraph import ParagraphChunker
            return ParagraphChunker().split(text, **params)

        chunks: list[ChunkResult] = []
        idx = 0

        for question, answer in pairs:
            # Build content: combine Q and A into one chunk
            parts = []
            if question:
                parts.append(question)
            if answer:
                parts.append(answer)

            content = "\n\n".join(parts)

            if len(content) < min_size:
                continue
            if len(content) > max_size:
                # Truncate very long answers
                content = content[:max_size] + "..."

            chunks.append(ChunkResult(
                index=idx,
                content=content,
                token_count=len(content) // 2,
                metadata={
                    "strategy": "qa_pair",
                    "has_question": bool(question),
                    "has_answer": bool(answer),
                    "question_preview": question[:100] if question else "",
                    "answer_length": len(answer),
                },
            ))
            idx += 1

        return chunks
