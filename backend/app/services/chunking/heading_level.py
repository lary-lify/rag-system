"""
Heading Level Chunking - split by markdown/HTML heading hierarchy.
Best for documents with clear heading structure (markdown, HTML, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult


@dataclass
class HeadingSection:
    """A section under a specific heading."""
    level: int
    title: str
    content: str
    start_line: int = 0


class HeadingLevelChunker(BaseChunkingStrategy):
    """Split text by heading levels (# ## ### or H1/H2 tags)."""

    name = "heading_level"

    def get_default_params(self) -> dict:
        return {
            "min_section_size": 50,
            "max_heading_depth": 6,
            "include_title_in_content": True,
            # Heading patterns to detect:
            "heading_patterns": [
                r'^(#{1,6})\s+(.+)$',           # Markdown: # Title
                r'^(<h[1-6]>)(.+?)(</h[1-6]>)',  # HTML: <h1>Title</h1>
                r'^([一二三四五六七八九十]+[、.])\s*(.+)',  # Chinese numbered headings
                r'^(\d+\.\d+[\.\s])(.+)',          # Numbered sections like 1.1, 2.3
            ],
        }

    def _detect_headings(self, text_lines: list[str], patterns: list[str]) -> list[tuple[int, int, str]]:
        """
        Detect headings in text lines.
        Returns list of (line_index, heading_level, heading_text).
        """
        results = []
        for i, line in enumerate(text_lines):
            for pattern in patterns:
                m = re.match(pattern, line.strip())
                if m:
                    # R-02 修复：原代码用 `pattern.startswith(r'^#')` 判断 markdown，
                    # 但 pattern 实际字符串前缀是 `^(#{1,6})`（以 `^(#` 开头），
                    # 导致该分支永远走不到、所有 markdown 标题被错判为 level=1。
                    # 修正为匹配真实前缀 `^(#`；HTML 分支前缀 `^(<h` 不变。
                    if pattern.startswith(r'^(#'):
                        # Markdown: group(1) 是 '#' 的个数，即标题层级
                        level = len(m.group(1))
                        title = m.group(2).strip()
                    elif pattern.startswith(r'^(<h'):
                        level = int(m.group(1)[2])
                        title = m.group(2).strip()
                    else:
                        level = 1  # Chinese/numbered headings 无层级信息，默认 1
                        title = (m.group(2) if (m.lastindex or 0) >= 2 else m.group(0)).strip()

                    results.append((i, level, title))
                    break  # first match wins per line
        return results

    def split(self, text: str, **params) -> list[ChunkResult]:
        patterns = params.get("heading_patterns", self.get_default_params()["heading_patterns"])
        min_size = params.get("min_section_size", 50)
        include_title = params.get("include_title_in_content", True)

        lines = text.split('\n')
        headings = self._detect_headings(lines, patterns)

        if not headings:
            # No headings found - fall back to paragraph splitting
            from app.services.chunking.paragraph import ParagraphChunker
            return ParagraphChunker().split(text, **params)

        chunks: list[ChunkResult] = []
        idx = 0

        for h_idx, (line_no, level, title) in enumerate(headings):
            start = line_no + 1  # skip the heading line itself
            end = headings[h_idx + 1][0] if h_idx + 1 < len(headings) else len(lines)

            section_text = '\n'.join(lines[start:end]).strip()
            if not section_text and end - start < min_size:
                continue

            # Build content with optional title prefix
            if include_title:
                full_content = f"{title}\n{section_text}"
            else:
                full_content = section_text

            chunks.append(ChunkResult(
                index=idx,
                content=full_content,
                token_count=len(full_content) // 2,
                metadata={
                    "heading_level": level,
                    "heading_title": title,
                    "start_line": start,
                    "end_line": end,
                },
            ))
            idx += 1

        return chunks
