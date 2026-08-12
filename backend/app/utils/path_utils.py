"""
Project path utilities.

Locates the project root by walking up from this file. For the RAG system the
authoritative marker is the repository-root `.env` (located at `rag-kb-system/.env`),
NOT `backend/requirements.txt`, so we prioritise `.env` and fall back to `.git`.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=None)
def find_project_root() -> Path:
    """向上查找项目根目录（以 .env 或 .git 所在目录为准）。"""
    start = Path(__file__).resolve().parent

    # 1) 优先以 .env 定位仓库根（RAG 后端 .env 在仓库根，而非 backend/）
    current = start
    while current != current.parent:
        if (current / ".env").exists():
            return current
        current = current.parent

    # 2) 退而求其次：以 .git 定位
    current = start
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # 3) 保守回退：本文件的上两级（backend/..）
    return start.parent.parent


def to_absolute_path(file_path: str) -> str:
    """将相对路径转换为基于项目根目录的绝对路径。"""
    if file_path is None:
        return file_path
    if Path(file_path).is_absolute():
        return file_path
    return str(find_project_root() / file_path)
