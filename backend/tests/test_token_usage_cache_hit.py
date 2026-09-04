"""
答案缓存命中落库 + 对账聚合验证。

用 SQLite 内存库（同步引擎，零外部依赖）验证：
- TokenUsage.cache_hit 列可建表、可写入、可读取；
- 不显式指定时 server_default=False（老行/embedding/chunking 写入安全）；
- 与 reports.get_cost_summary / get_usage_trend 同款的 case 求和聚合 SQL 正确统计命中数。

注：reports 端点直接跑这条 case-sum 查询，这里在真实 SQL 引擎上验证其语义，
避免只靠推理下结论（项目约定：修复须有验证脚本实测）。
"""
import pytest
from sqlalchemy import create_engine, select, func, case
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.token_usage import TokenUsage, TokenType


@pytest.fixture
def sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)  # 建全部表，含 cache_hit 列
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s
    engine.dispose()


def _seed(s):
    # chat：3 命中 + 2 未命中；embedding 2 条（不应计入命中）
    # 注：模型 id 是 BigInteger+autoincrement，MySQL 下 OK；SQLite 内存库 BIGINT PK 不隐式自增，
    # 故这里显式给定 id（仅测试脚手架需要，不影响生产语义）。
    rows = [
        TokenUsage(id=1, type=TokenType.chat, user_id=1, kb_id=10, input_tokens=0, output_tokens=0, estimated_cost=0.0, cache_hit=True),
        TokenUsage(id=2, type=TokenType.chat, user_id=1, kb_id=10, input_tokens=0, output_tokens=0, estimated_cost=0.0, cache_hit=True),
        TokenUsage(id=3, type=TokenType.chat, user_id=2, kb_id=11, input_tokens=0, output_tokens=0, estimated_cost=0.0, cache_hit=True),
        TokenUsage(id=4, type=TokenType.chat, user_id=2, kb_id=11, input_tokens=120, output_tokens=80, estimated_cost=0.001, cache_hit=False),
        TokenUsage(id=5, type=TokenType.chat, user_id=1, kb_id=10, input_tokens=90, output_tokens=60, estimated_cost=0.0008, cache_hit=False),
        TokenUsage(id=6, type=TokenType.embedding, user_id=1, input_tokens=500, output_tokens=0, estimated_cost=0.0005),  # 无 cache_hit
    ]
    s.add_all(rows)
    s.commit()


def test_column_exists_and_roundtrip(sqlite_session):
    _seed(sqlite_session)
    # 不指定 cache_hit 的 embedding 行应取 server_default=False
    emb = sqlite_session.execute(
        select(TokenUsage).where(TokenUsage.type == TokenType.embedding)
    ).scalar_one()
    assert emb.cache_hit is False

    hits = sqlite_session.execute(
        select(TokenUsage).where(TokenUsage.cache_hit == True)  # noqa: E712
    ).scalars().all()
    assert len(hits) == 3


def test_reports_case_sum_aggregation(sqlite_session):
    """reports 端点用的同款 case 求和：按 type 统计命中数。"""
    _seed(sqlite_session)
    rows = sqlite_session.execute(
        select(
            TokenUsage.type,
            func.sum(case((TokenUsage.cache_hit == True, 1), else_=0)).label("hits"),  # noqa: E712
        ).group_by(TokenUsage.type)
    ).all()
    by_type = {t: int(h or 0) for t, h in rows}
    # chat 命中 3，embedding 命中 0
    assert by_type[TokenType.chat] == 3
    assert by_type[TokenType.embedding] == 0


def test_cost_summary_totals(sqlite_session):
    """cost-summary 顶层 total_cache_hits / total_cache_misses 语义。"""
    _seed(sqlite_session)
    chat_rows = sqlite_session.execute(
        select(TokenUsage).where(TokenUsage.type == TokenType.chat)
    ).scalars().all()
    hits = sum(1 for r in chat_rows if r.cache_hit)
    misses = sum(1 for r in chat_rows if not r.cache_hit)
    assert hits == 3
    assert misses == 2
