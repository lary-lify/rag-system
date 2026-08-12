"""
Base chunking strategy interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkResult:
    """Single text chunk output."""
    index: int
    content: str
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


class BaseChunkingStrategy(ABC):
    """Abstract base for all chunking strategies."""

    name: str = "base"

    @abstractmethod
    def split(self, text: str, **params) -> list[ChunkResult]:
        """Split input text into chunks. Returns list of ChunkResult."""
        ...

    @abstractmethod
    def get_default_params(self) -> dict:
        """Return default parameters for this strategy."""
        ...
