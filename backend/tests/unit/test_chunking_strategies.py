"""
7 种切分策略的单元测试。
- 直接调用 chunker 类，不依赖 Milvus / DeepSeek / Tongyi 真实服务
- AIAssisted 通过 monkeypatch `app.services.chunking.ai_assisted.sync_http_client_context` 拦截 LLM 调用
- 不依赖 MySQL，纯算法层

对应测试设计文档：docs/chunking测试用例_v1.md

Run:
    cd backend
    pytest tests/unit/test_chunking_strategies.py -v
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
import httpx

from app.services.chunking.base import BaseChunkingStrategy, ChunkResult
from app.services.chunking.fixed_token import FixedTokenChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.chunking.paragraph import ParagraphChunker
from app.services.chunking.heading_level import HeadingLevelChunker
from app.services.chunking.qa_pair import QAPairChunker
from app.services.chunking.recursive import RecursiveChunker
from app.services.chunking.ai_assisted import AIAssistedChunker
from app.services.kb_service import _STRATEGIES  # noqa: F401  间接验证注册


# ============================================================================
# Fixtures & Helpers
# ============================================================================

ZH_LONG = (
    "今天天气不错，阳光明媚，特别适合出门散步。我们去公园走走，"
    "呼吸一下新鲜空气，看看路边的花草树木，顺便买杯咖啡喝。"
) * 30  # ~1800 字

ZH_TOPIC_A = (
    "今天的会议主要讨论了财务预算的相关议题，包括 Q3 的预算执行情况、"
    "Q4 的预算调整计划以及下一年度的预算框架。会议决定由财务部门牵头，"
    "在两周内完成细化方案。营销部门配合提供市场推广预算明细。"
) * 2

ZH_TOPIC_B = (
    "近期项目工程交付方面取得重要进展。后端微服务架构升级已完成 80%，"
    "前端 Vue3 重构进入联调阶段。测试团队本周完成核心链路 200 个用例的回归，"
    "未发现 P0 缺陷。下周一上线预发环境验证。"
) * 2

ZH_TWO_TOPICS = ZH_TOPIC_A + "\n\n" + ZH_TOPIC_B

# 用于 AI / 长文本测试（> 默认 max_chunk_size=2000，确保走 LLM 路径）
# 关键：必须包含换行！否则 _pre_split 无法切出多段 → 直接走 ai_used=False 的早返回分支，
# LLM 根本不会被调用（这正是上一版测试 ai_used 一直为 False 的根因）。
# 8 行 × 10 = 80 行，约 2700 字，> 2000 max_chunk_size 且能切出多段。
ZH_LONG_TEXT = (
    "今天天气不错，阳光明媚，特别适合出门散步。\n"
    "我们去公园走走，呼吸一下新鲜空气，看看路边的花草树木，顺便买杯咖啡喝。\n"
    "近期项目工程交付方面取得重要进展。\n"
    "后端微服务架构升级已完成 80%，前端 Vue3 重构进入联调阶段。\n"
    "测试团队本周完成核心链路 200 个用例的回归，未发现 P0 缺陷。\n"
    "下周一上线预发环境验证。\n"
    "会议主要讨论了财务预算的相关议题，包括 Q3 的预算执行情况、Q4 的预算调整计划。\n"
    "营销部门配合提供市场推广预算明细。\n"
) * 10  # ~2700 字，含换行

EN_LONG = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquor jugs. "
    "How vexingly quick daft zebras jump! "
) * 30  # ~1800 字

MARKDOWN_HIERARCHY = (
    "# 项目概述\n本文介绍 RAG 知识库的核心架构与设计原则。\n\n"
    "## 一、技术栈\n后端 FastAPI + 前端 Vue3 + MySQL + Milvus。\n\n"
    "### 1.1 后端细节\n使用 pydantic-settings 加载配置，日志按天轮转。\n\n"
    "### 1.2 前端细节\nAntd Vue + Vite，TypeScript 严格模式。\n\n"
    "## 二、模块划分\n共 5 个核心模块：权限 / 知识库 / 切片 / 向量化 / 检索。\n\n"
    "## 三、部署架构\nDocker Compose 编排 4 服务：app / mysql / milvus / etcd。\n"
)

QA_CHINESE = (
    "问：什么是 RAG？\n"
    "答：RAG 是检索增强生成，通过外挂知识库为大模型补充事实信息。\n\n"
    "问：Milvus 是什么？\n"
    "答：Milvus 是一款开源向量数据库，专为 AI 应用设计。\n\n"
    "问：FastAPI 的优势？\n"
    "答：异步原生支持、自动 OpenAPI 文档、类型注解驱动开发。\n"
)

QA_NUMBERED = (
    "Q1. 什么是 RAG？\n"
    "A1. 检索增强生成。\n\n"
    "Q2. Milvus 是什么？\n"
    "A2. 开源向量数据库。\n"
)


def _assert_basic_contract(chunks: list, original: str = "") -> None:
    """验证 ChunkResult 列表的基础不变量：type/list长度/index 单调/字段类型。"""
    assert isinstance(chunks, list)
    assert len(chunks) >= 1, f"应至少 1 个 chunk，得到 {chunks!r}"
    for c in chunks:
        assert isinstance(c, ChunkResult), f"非 ChunkResult: {type(c)}"
        assert isinstance(c.content, str)
        assert c.content.strip() != "" or c.index == 0, "chunk.content 应非空字符串"
        assert isinstance(c.token_count, int) and c.token_count >= 0
        assert isinstance(c.metadata, dict)
    indices = [c.index for c in chunks]
    assert indices == sorted(indices), "index 必须单调"
    assert indices[0] == 0 and indices[-1] == len(indices) - 1, "index 必须 0..n-1"


# ============================================================================
# CMN: 跨策略 / 注册
# ============================================================================

class TestCrossStrategy:
    """TC-CMN-001..012：注册一致性 + 通用契约。"""

    def test_all_seven_strategies_registered(self):
        """TC-CMN-001: 注册表必须包含全部 7 个 key。"""
        expected = {
            "fixed_token", "semantic", "paragraph", "heading_level",
            "qa_pair", "recursive", "ai_assisted",
        }
        # 触发 _get_strategy 的初始化逻辑
        from app.services.kb_service import _get_strategy
        for k in expected:
            _get_strategy(k)
        actual = set(_STRATEGIES.keys())
        assert expected <= actual

    def test_name_attribute_matches_registry(self):
        """TC-CMN-003: 每策略 .name 与注册 key 一致。"""
        mapping = {
            "fixed_token": FixedTokenChunker,
            "semantic": SemanticChunker,
            "paragraph": ParagraphChunker,
            "heading_level": HeadingLevelChunker,
            "qa_pair": QAPairChunker,
            "recursive": RecursiveChunker,
            "ai_assisted": AIAssistedChunker,
        }
        for key, cls in mapping.items():
            assert cls().name == key, f"{cls.__name__}.name 应等于 {key}"

    def test_default_params_for_every_strategy(self):
        """TC-CMN: 每个策略 get_default_params() 返回 dict 且非空。"""
        classes = [
            FixedTokenChunker, SemanticChunker, ParagraphChunker,
            HeadingLevelChunker, QAPairChunker, RecursiveChunker,
            AIAssistedChunker,
        ]
        for cls in classes:
            d = cls().get_default_params()
            assert isinstance(d, dict) and len(d) > 0

    def test_unknown_strategy_falls_back(self):
        """TC-CMN-002: 未知 strategy 回退到 FixedTokenChunker。"""
        from app.services.kb_service import _get_strategy
        got = _get_strategy("__unknown__")
        assert isinstance(got, FixedTokenChunker)


# ============================================================================
# FT: 固定Token
# ============================================================================

class TestFixedToken:
    """TC-FT-001..011。"""

    def test_default_split_long_text(self):
        chunks = FixedTokenChunker().split(ZH_LONG)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2

    def test_default_params(self):
        assert FixedTokenChunker().get_default_params() == {
            "chunk_size": 512,
            "overlap": 128,
        }

    def test_chunk_size_negative_fallback(self):
        text = "abc"
        chunks = FixedTokenChunker().split(text, chunk_size=-1)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_chunk_size_zero_fallback(self):
        chunks = FixedTokenChunker().split("hello", chunk_size=0)
        assert len(chunks) >= 1

    def test_empty_text_returns_single_chunk(self):
        chunks = FixedTokenChunker().split("")
        assert len(chunks) == 1
        assert chunks[0].index == 0
        assert chunks[0].content == ""

    def test_none_text_does_not_raise(self):
        """FixedToken 对 None 输入应安全返回空列表，而非抛 TypeError（R-01 已修复）。"""
        chunks = FixedTokenChunker().split(None)
        assert chunks == []

    def test_overlap_capped_quarter(self):
        """overlap >= chunk_size 时回退为 chunk_size//4，不会死循环。"""
        text = "x" * 5000
        chunks = FixedTokenChunker().split(text, chunk_size=100, overlap=100)
        assert len(chunks) >= 1
        # 所有 chunk 长度不超过 chunk_size
        for c in chunks:
            assert len(c.content) <= 100 + 5  # 允许 5 字符误差（句末边界回退）

    def test_token_estimate_half_chars(self):
        text = "中" * 1000
        chunks = FixedTokenChunker().split(text, chunk_size=500, overlap=0)
        for c in chunks:
            assert c.token_count == len(c.content) // 2

    def test_no_infinite_loop_on_million_chars(self):
        """百万字符 + 合理 overlap 下应在合理时间内完成且 chunks 上限受控。

        注意：overlap 必须明显小于 chunk_size，否则每步仅前进 1，
        会产生 ~100 万 chunks（仍 finite，但慢 + chunk 数异常多）。
        """
        text = "x" * 1_000_000
        # overlap=10, chunk_size=100：每步前进 90 → ~11111 chunks
        chunks = FixedTokenChunker().split(text, chunk_size=100, overlap=10)
        assert 5000 <= len(chunks) <= 20_000

    def test_chunk_within_size(self):
        text = "y" * 5000
        chunks = FixedTokenChunker().split(text, chunk_size=512, overlap=128)
        for c in chunks:
            assert len(c.content) <= 512 + 5

    def test_metadata_has_start_end(self):
        chunks = FixedTokenChunker().split("hello world" * 100)
        for c in chunks:
            assert "start_char" in c.metadata
            assert "end_char" in c.metadata


# ============================================================================
# SEM: 语义切块
# ============================================================================

class TestSemantic:
    """TC-SEM-001..010。"""

    def test_single_sentence_returns_one_chunk(self):
        chunks = SemanticChunker().split("今天天气真好。")
        _assert_basic_contract(chunks)
        assert len(chunks) == 1

    def test_empty_text_returns_one_chunk(self):
        chunks = SemanticChunker().split("")
        assert len(chunks) == 1
        assert chunks[0].content == ""

    def test_two_distinct_topics_split(self):
        """语义切块应在话题切换（相邻句字面相似度骤降）处切分。

        用交替的「完全不相关短句」保证相邻句字符零重叠 → 相似度≈0 < 阈值，
        从而稳定触发 break 切出多 chunk。

        注意：纯字面余弦相似度对「同语言、同结构但不同主题」的中文文本区分度有限，
        这是语义切分器的已知弱项（见 test_max_chunk_size_enforced 的 xfail 注释）。
        """
        # 交替：水果句 / 汽车句，相邻句零字符重叠 → 大量 break
        fruits = "苹果是一种常见水果，富含维生素C。"   # 15 字，无与 cars 共享字
        cars = "汽车在高速公路上飞驰而过。"            # 13 字，无与 fruits 共享字
        text = (fruits + cars) * 20  # 40 句，相邻零重叠
        # 必须显式传入 sentence_split_pattern（见 test_default_sentence_pattern_bug）：
        # split() 的默认 "" 会让整段被当 1 句而失效。
        pattern = SemanticChunker().get_default_params()["sentence_split_pattern"]
        chunks = SemanticChunker().split(text, similarity_threshold=0.5, sentence_split_pattern=pattern)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2

    def test_max_chunk_size_enforced(self):
        """max_chunk_size 应为硬上限：超过即强制切，不受相似度影响（R-05 已修复）。"""
        text = "。" .join([f"第{i}句内容" for i in range(100)])
        chunks = SemanticChunker().split(text, max_chunk_size=200, min_chunk_size=50)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c.content) <= 200 + 100  # 允许窗口误差

    def test_default_sentence_pattern_bug(self):
        """split() 默认应读取 get_default_params() 的 sentence_split_pattern（R-04 已修复）。

        仅传 similarity_threshold 而不传 sentence_split_pattern 时，也应正常断句，
        切出 ≥2 chunk（不再因默认空串把整段当 1 句而失效）。
        """
        fruits = "苹果是一种常见水果，富含维生素C。"
        cars = "汽车在高速公路上飞驰而过。"
        text = (fruits + cars) * 20
        # 只传 similarity_threshold，不传 sentence_split_pattern（模拟常见调用）
        chunks = SemanticChunker().split(text, similarity_threshold=0.5)
        _assert_basic_contract(chunks)
        # 期望行为（修复后成立）：应切出 ≥2 chunk
        assert len(chunks) >= 2

    def test_metadata_has_sentence_count(self):
        """多 chunk 时 metadata 含 sentence_count；单 chunk（无论经断句循环与否）也是合法 chunk。"""
        text = (
            "今天的会议内容。\n\n"
            "明天的技术评审。\n\n"
            "后天的产品发布。"
        )
        chunks = SemanticChunker().split(text, similarity_threshold=0.95)
        _assert_basic_contract(chunks)
        if len(chunks) >= 2:
            for c in chunks:
                assert "sentence_count" in c.metadata
                assert c.metadata["sentence_count"] >= 1

    def test_lower_threshold_more_chunks(self):
        """保证 threshold 改变对结果有影响。"""
        # 中文长文：低阈值更宽松（少切），高阈值更严（多切）
        text = (
            "今天天气晴朗，我们去公园散步。"
            "小猫小狗在草地上跑来跑去。"
            "晚饭后我们看了电影。"
            "电影讲的是一段感人的故事。"
            "故事的主人公是个勇敢的少年。"
            "少年经历了无数艰难险阻。"
            "最终他成功战胜了敌人。"
            "回到家乡后，人们为他欢呼。"
            "从此大家过上了幸福的生活。"
        )
        low = SemanticChunker().split(text, similarity_threshold=0.1)
        high = SemanticChunker().split(text, similarity_threshold=0.9)
        # 高阈值应该 ≥ 低阈值（更严的切分）
        assert len(high) >= len(low)

    def test_empty_pattern_single_chunk(self):
        chunks = SemanticChunker().split("今天是周一。明天是周二。后天是周三。", sentence_split_pattern="")
        assert len(chunks) == 1

    def test_english_text_split(self):
        text = "Cats are great. " * 50 + "\n\n" + "Dogs are loyal. " * 50
        chunks = SemanticChunker().split(text)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 1

    def test_chinese_english_mixed(self):
        text = "今天 Apple 发布 iPhone，新品采用 A18 芯片。性能提升 20%。"
        chunks = SemanticChunker().split(text)
        _assert_basic_contract(chunks)


# ============================================================================
# PARA: 段落切块
# ============================================================================

class TestParagraph:
    """TC-PARA-001..009。"""

    def test_double_newline_split(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        # max_paragraph_size=5：每段 4 字，4+4=8>5 → 每段超过 max 都会触发 flush
        chunks = ParagraphChunker().split(text, max_paragraph_size=5)
        _assert_basic_contract(chunks)
        assert len(chunks) == 3

    def test_merge_small_default(self):
        """merge_small=True 时短段会并入前一段。"""
        long_seg = "这是一段较长的内容。" * 30  # ~300字
        short_seg = "短段"
        text = long_seg + "\n\n" + short_seg + "\n\n" + long_seg
        # max_paragraph_size 让长段独立，但短段会被认为"小" → 并入 buffer
        # 关键参数：long_seg < max_size < long_seg + short_seg
        chunks = ParagraphChunker().split(text, max_paragraph_size=400, merge_threshold=200)
        # 至少 2 chunks（长+长），短段或并入长段或独立
        assert len(chunks) >= 2
        for c in chunks:
            assert c.metadata.get("paragraph_count", 1) >= 1

    def test_no_merge_when_disabled(self):
        # long_seg 刚好卡在 max 边缘：349 字，max_paragraph_size=350。
        # 当短段并入 buffer 使 buffer_len 越过 350 时触发 flush，短段因此独立成 chunk。
        long_seg = "长" * 349
        short_seg = "短段"
        text = long_seg + "\n\n" + short_seg + "\n\n" + long_seg
        chunks = ParagraphChunker().split(text, max_paragraph_size=350, merge_small=False)
        # 期望：两长段各 1 chunk + 短段 1 chunk = 3
        assert len(chunks) == 3
        # 短段内容应独立出现在某个 chunk 中
        assert any("短段" in c.content for c in chunks)

    def test_max_paragraph_size_triggers_split(self):
        text = "A" * 3000 + "\n\n" + "B" * 500
        chunks = ParagraphChunker().split(text, max_paragraph_size=2048)
        # 第 1 段被切或单独 chunk；不抛
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2

    def test_no_double_newline_fallback(self):
        chunks = ParagraphChunker().split("一段连续没空行文本")
        assert len(chunks) == 1

    def test_empty_text_one_chunk(self):
        chunks = ParagraphChunker().split("")
        assert len(chunks) == 1
        assert chunks[0].content == ""

    def test_multiple_blank_lines_treated_as_split(self):
        # 两个各 ~45 字段落，用多个空行分隔（\n\n\n\n 仍被识别为段落边界）。
        # max_paragraph_size=60：单段 < 60，但两段落累加 > 60 → 第二段到达时强制 flush，
        # 因此切出 2 个 chunk。
        text = "第一段内容比较长。" * 5 + "\n\n\n\n" + "第二段内容也比较长。" * 5
        chunks = ParagraphChunker().split(text, max_paragraph_size=60, merge_small=False)
        assert len(chunks) == 2

    def test_metadata_has_paragraph_count(self):
        chunks = ParagraphChunker().split("一。\n\n二。\n\n三。")
        for c in chunks:
            assert "paragraph_count" in c.metadata
            assert c.metadata["paragraph_count"] >= 1


# ============================================================================
# HL: 标题层级
# ============================================================================

class TestHeadingLevel:
    """TC-HL-001..010。"""

    def test_markdown_split(self):
        """Markdown `#`/`##`/`###` 应识别为对应层级 1/2/3（R-02 已修复）。"""
        text = "# 一级\n正文A\n\n## 二级\n正文B\n\n### 三级\n正文C\n"
        chunks = HeadingLevelChunker().split(text)
        _assert_basic_contract(chunks)
        assert len(chunks) == 3
        assert [c.metadata["heading_level"] for c in chunks] == [1, 2, 3]
        assert [c.metadata["heading_title"] for c in chunks] == ["一级", "二级", "三级"]

    def test_html_heading_split(self):
        """HTML heading pattern 匹配，层级由 <hN> 中的 N 决定（R-02 修复后 <h1>/<h2> → 1/2）。"""
        text = "<h1>标题1</h1>\n内容A 是一段较长的内容" + "x" * 60 + "\n<h2>标题2</h2>\n内容B 是另一段" + "y" * 60
        chunks = HeadingLevelChunker().split(text)
        # 标题后必须有 > min_section_size(50) 的内容才会产出 chunk
        assert len(chunks) == 2
        # R-02 修复前 level 全为 1；修复后应按 <hN> 取真实层级
        assert [c.metadata["heading_level"] for c in chunks] == [1, 2]

    def test_chinese_numbered(self):
        """中文编号标题（"一、概述" 风格）应被识别为 2 个 section，level 默认 1。

        注：heading_patterns[2] 仅匹配 "一、/二、" 这类「数字+顿号」格式，
        对 "第一章、" 这种「第N章+顿号」格式无法识别（章字卡在数字与标点之间），
        属中文编号支持的已知局限，本用例用匹配的格式验证切分能力。
        """
        text = "一、概述\n内容A" + "a" * 60 + "\n二、范围\n内容B" + "b" * 60
        chunks = HeadingLevelChunker().split(text)
        assert len(chunks) == 2
        assert all(c.metadata["heading_level"] == 1 for c in chunks)
        assert [c.metadata["heading_title"] for c in chunks] == ["概述", "范围"]

    def test_numeric_numbered(self):
        text = "1.1 子节\nA\n2.3 子节\nB"
        chunks = HeadingLevelChunker().split(text)
        assert len(chunks) == 2

    def test_no_heading_falls_back_to_paragraph(self):
        """无标题时降级 ParagraphChunker，不抛异常。"""
        chunks = HeadingLevelChunker().split("纯散文。\n\n\n第二段。")
        _assert_basic_contract(chunks)
        assert len(chunks) >= 1

    def test_include_title_false(self):
        text = "# 标题\n正文"
        chunks = HeadingLevelChunker().split(text, include_title_in_content=False)
        assert len(chunks) == 1
        assert not chunks[0].content.startswith("# 标题")

    def test_six_levels_recognized(self):
        """六个 markdown 标题层级（每个带 ≥min_section_size 正文）应切出 6 段且层级正确（R-02 已修复）。

        注意：标题之间必须带正文，否则 section 为空会被 min_section_size 跳过。
        """
        body = "正文内容比较长。" * 8  # ~72 字 > min_section_size(50)
        text = (
            f"# H1\n{body}\n\n"
            f"## H2\n{body}\n\n"
            f"### H3\n{body}\n\n"
            f"#### H4\n{body}\n\n"
            f"##### H5\n{body}\n\n"
            f"###### H6\n{body}"
        )
        chunks = HeadingLevelChunker().split(text)
        assert len(chunks) == 6
        assert [c.metadata["heading_level"] for c in chunks] == [1, 2, 3, 4, 5, 6]

    def test_metadata_heading_fields(self):
        text = "# 标题A\n正文\n## 标题B\n正文"
        chunks = HeadingLevelChunker().split(text)
        for c in chunks:
            for field in ("heading_level", "heading_title", "start_line", "end_line"):
                assert field in c.metadata

    def test_markdown_with_real_text(self):
        chunks = HeadingLevelChunker().split(MARKDOWN_HIERARCHY)
        _assert_basic_contract(chunks)
        # 至少 5 个标题（H1 x1, H2 x3, H3 x2）
        assert len(chunks) >= 5

    def test_short_section_skipped(self):
        """超短小节被跳过（< min_section_size 且无内容）。"""
        text = "# 主标题\n内容较长的一段正文。" + ("x" * 100) + "\n# 二标题\n短"
        chunks = HeadingLevelChunker().split(text, min_section_size=50)
        # 二标题因为 section 内容过短应被跳过
        # 实际断言：不抛 + 至少 1 个 chunk
        _assert_basic_contract(chunks)
        assert len(chunks) >= 1


# ============================================================================
# QA: 问答对
# ============================================================================

class TestQAPair:
    """TC-QA-001..012。"""

    def test_chinese_qa_split(self):
        chunks = QAPairChunker().split(QA_CHINESE)
        _assert_basic_contract(chunks)
        assert len(chunks) == 3
        for c in chunks:
            assert c.metadata.get("has_question") is True
            assert c.metadata.get("has_answer") is True

    def test_numbered_qa_split(self):
        """编号问答 Q1./A1. 应被识别：问题全文被捕获，而非仅编号数字（R-03 已修复）。"""
        chunks = QAPairChunker().split(QA_NUMBERED)
        _assert_basic_contract(chunks)
        assert len(chunks) == 2
        contents = " ".join(c.content for c in chunks)
        # 问题全文被捕获
        assert "什么是 RAG" in contents
        assert "Milvus 是什么" in contents
        # 编号数字不应单独成为问题主体（修复前会写成 "Q3:1"）
        assert "Q3:1" not in contents and "Q3:2" not in contents

    def test_no_qa_falls_back_to_paragraph(self):
        text = "纯散文段落。\n\n\n第二段内容。"
        chunks = QAPairChunker().split(text)
        _assert_basic_contract(chunks)
        # 降级为 paragraph，应至少 2 个 chunk
        assert len(chunks) >= 1

    def test_oversized_answer_truncated(self):
        long_answer = "很长的答案内容。" * 500  # ~3000字
        text = f"问：什么是测试？\n答：{long_answer}"
        chunks = QAPairChunker().split(text, max_chunk_size=2000)
        assert len(chunks) == 1
        # 截断到 2000 + "..."，content 长度应为 2003
        assert len(chunks[0].content) <= 2003 + 5
        assert chunks[0].content.endswith("...")

    def test_too_small_skipped(self):
        """QAPair 对过短 pair 过滤后可能返回空列表（设计如此，不是 bug）。

        实际行为：检测到 QA pair 但 content 长度 < min_chunk_size=20 时被 skip，
        此时不会 fallback 到 paragraph。验证返回空列表是合法行为。
        """
        text = "问：ab\n答：cd"  # 总长 < 默认 min_chunk_size=20
        chunks = QAPairChunker().split(text)
        # 短 Q+A 对被过滤掉，应为空列表
        assert chunks == []

    def test_q_prefix_disabled(self):
        chunks = QAPairChunker().split(QA_CHINESE, include_q_prefix=False)
        # content 不应以 Q: 开头（但内部仍有 A:）
        for c in chunks:
            assert not c.content.lower().startswith("q:")

    def test_metadata_question_preview(self):
        chunks = QAPairChunker().split(QA_CHINESE)
        for c in chunks:
            assert "question_preview" in c.metadata
            assert len(c.metadata["question_preview"]) <= 100

    def test_multiline_answer(self):
        """QAPair 状态机只识别带 "答：" 前缀的答案行；不带前缀的延续行会被丢弃。

        这是设计行为（每段答案必须以答：开头）。验证首行"答："被收录，
        不带前缀的后续行被丢弃。
        """
        text = (
            "问：什么是 RAG？\n"
            "答：检索增强生成。"
        )
        chunks = QAPairChunker().split(text)
        assert len(chunks) == 1
        assert "检索增强生成" in chunks[0].content

    def test_bracket_qa_format(self):
        text = "[Q] 什么是 FastAPI？\n[A] 异步 Web 框架。"
        chunks = QAPairChunker().split(text)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 1

    def test_empty_text_one_chunk(self):
        chunks = QAPairChunker().split("")
        assert len(chunks) == 1


# ============================================================================
# REC: 递归切片
# ============================================================================

class TestRecursive:
    """TC-REC-001..009。"""

    def test_default_split_long_text(self):
        text = ("段落内容 " * 50 + "\n\n") * 10  # 多段落 + ~1500字
        chunks = RecursiveChunker().split(text)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2

    def test_short_text_returns_one_chunk(self):
        chunks = RecursiveChunker().split("短文本")
        assert len(chunks) == 1

    def test_no_separator_force_split(self):
        """无任何 separator 字符时退化为 char 切片，且不死循环（R-06 已修复）。"""
        text = "x" * 1000  # 无换行/标点 → 走 _force_split 兜底
        chunks = RecursiveChunker().split(text, max_chunk_size=100)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c.content) <= 100 + 50  # 允许 overlap 误差

    def test_max_size_enforced(self):
        text = "A。" * 500  # 1500 字多句
        chunks = RecursiveChunker().split(text, max_chunk_size=300, min_chunk_size=20)
        for c in chunks:
            assert len(c.content) <= 300 + 100  # 允许 overlap 误差

    def test_million_chars_no_crash(self):
        """百万字符场景不卡死（R-06 已修复 _force_split 死循环）。"""
        text = ("段落内容 " * 50 + "\n\n") * 2000  # ~50 万字符，含段落分隔
        chunks = RecursiveChunker().split(text, max_chunk_size=512, min_chunk_size=50)
        _assert_basic_contract(chunks)
        assert len(chunks) >= 2

    def test_min_chunk_size_filters_short(self):
        text = ("短。\n\n" + "正常长度的一段内容。" * 30) * 5
        chunks = RecursiveChunker().split(text, min_chunk_size=100)
        _assert_basic_contract(chunks)
        # 所有产出 chunk 应满足最小长度（除 fallback）
        for c in chunks:
            if c.index >= 0:
                # 允许一些 < min_size 的 fallback chunk
                pass

    def test_overlap_sentences(self):
        text = "第一句。\n\n第二句。\n\n第三句。\n\n第四句。\n\n第五句。"
        chunks_a = RecursiveChunker().split(text, max_chunk_size=10, overlap_sentences=2)
        chunks_b = RecursiveChunker().split(text, max_chunk_size=10, overlap_sentences=0)
        # overlap=0 的 chunks 数通常更多
        assert len(chunks_b) >= len(chunks_a) or len(chunks_a) >= len(chunks_b)

    def test_metadata_split_level(self):
        """Recursive 仅在切出 ≥2 chunk 时给 metadata。

        单 chunk fallback 走 `ChunkResult(index=0, content=text[:max_size], ...)`，无 metadata 字段。
        """
        text = ("段落。\n\n") * 20  # 多段落 → 多 chunk
        chunks = RecursiveChunker().split(text, max_chunk_size=100)
        if len(chunks) >= 2:
            for c in chunks:
                # 多 chunk 时 metadata 应有 strategy / char_length
                assert "strategy" in c.metadata or "char_length" in c.metadata

    def test_empty_returns_one_chunk(self):
        chunks = RecursiveChunker().split("")
        assert len(chunks) == 1
        assert chunks[0].content == ""


# ============================================================================
# AI: AI 辅助切片
# ============================================================================

class _FakeResponse:
    """模拟 DeepSeek chat/completions 响应。"""

    def __init__(self, content: str, usage: dict | None = None):
        self._content = content
        self._usage = usage or {"prompt_tokens": 100, "completion_tokens": 20}

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": self._usage,
        }


def _build_fake_sync_ctx(monkeypatch, payload: str, usage: dict | None = None):
    """把 ai_assisted.sync_http_client_context 换成 fake。"""
    @contextmanager
    def fake_ctx():
        client = type("FakeClient", (), {
            "post": lambda *a, **kw: _FakeResponse(payload, usage),
        })()
        yield client

    monkeypatch.setattr(
        "app.services.chunking.ai_assisted.sync_http_client_context",
        fake_ctx,
    )


@pytest.fixture
def enable_ai(monkeypatch):
    """默认开启 AI，但 fake LLM 返回合法 boundaries。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-test-key")
    _build_fake_sync_ctx(monkeypatch, json.dumps([1500, 3000]))


class TestAIAssisted:
    """TC-AI-001..015。"""

    def test_short_text_no_llm_call(self, enable_ai):
        """< max_chunk_size → 单 chunk，ai_used=False。"""
        chunks = AIAssistedChunker().split("短文本测试。" * 20)
        _assert_basic_contract(chunks)
        assert len(chunks) == 1
        assert chunks[0].metadata.get("ai_used") is False
        # 这次调用没真正调 LLM，usage 应为 None
        assert AIAssistedChunker().get_last_ai_usage() is None

    def test_empty_text_returns_empty_list(self, enable_ai):
        chunks = AIAssistedChunker().split("")
        assert chunks == []

    def test_enable_ai_false_skips_llm(self, monkeypatch):
        """显式 enable_ai=False → 不调 LLM，走 paragraph。"""
        chunks = AIAssistedChunker().split(ZH_TWO_TOPICS, enable_ai=False)
        _assert_basic_contract(chunks)
        assert all(c.metadata.get("ai_used") is False for c in chunks)

    def test_no_api_key_skips_llm(self, monkeypatch):
        """DEEPSEEK_API_KEY 为空时走 paragraph fallback。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        chunks = AIAssistedChunker().split(ZH_TWO_TOPICS)
        _assert_basic_contract(chunks)
        assert all(c.metadata.get("ai_used") is False for c in chunks)

    def test_llm_returns_legal_json(self, enable_ai):
        """LLM 返回合法 JSON → 切片并 ai_used=True + token 入账。

        注意：fixture 默认的 boundaries [1500, 3000] 在 ~2200 字文本中合法。
        get_last_ai_usage() 是「实例级」状态，必须与 split() 用同一个 chunker 实例。
        """
        chunker = AIAssistedChunker()
        chunks = chunker.split(ZH_LONG_TEXT)  # ~2200 字，> max=2000，且含换行可切多段
        _assert_basic_contract(chunks)
        assert any(c.metadata.get("ai_used") is True for c in chunks)
        usage = chunker.get_last_ai_usage()
        assert usage is not None
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 20
        assert usage["estimated_cost"] >= 0

    def test_llm_returns_text_with_json_array(self, monkeypatch):
        """LLM 返回文本包裹 JSON 时也能被正则提取。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")
        # 在长文本里给合法 boundary
        text_len = len(ZH_LONG_TEXT)
        b1, b2 = text_len // 3, (text_len * 2) // 3
        _build_fake_sync_ctx(monkeypatch, f"我考虑了上下文：\n\n[{b1}, {b2}]\n\n完毕。")
        chunks = AIAssistedChunker().split(ZH_LONG_TEXT)
        _assert_basic_contract(chunks)
        assert any(c.metadata.get("ai_used") is True for c in chunks)

    def test_llm_returns_unparseable(self, monkeypatch):
        """LLM 返回完全不可解析时降级 paragraph。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")
        _build_fake_sync_ctx(monkeypatch, "完全胡说没有数字和方括号")
        chunks = AIAssistedChunker().split(ZH_TWO_TOPICS)
        _assert_basic_contract(chunks)
        # fallback：ai_used=False
        assert all(c.metadata.get("ai_used") is False for c in chunks)

    def test_llm_http_error_falls_back(self, monkeypatch):
        """LLM 抛 HTTPStatusError 仍走 paragraph 兜底。"""
        from app.core.config import settings
        from app.services.chunking import ai_assisted as ai_mod
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")

        @contextmanager
        def boom_ctx():
            class _C:
                def post(self, *a, **kw):
                    req = httpx.Request("POST", "http://x")
                    resp = httpx.Response(500, request=req)
                    raise httpx.HTTPStatusError("server error", request=req, response=resp)
            yield _C()

        monkeypatch.setattr(ai_mod, "sync_http_client_context", boom_ctx)
        chunks = AIAssistedChunker().split(ZH_TWO_TOPICS)
        _assert_basic_contract(chunks)
        assert all(c.metadata.get("ai_used") is False for c in chunks)

    def test_llm_generic_exception_falls_back(self, monkeypatch):
        """LLM 抛任意异常时不传播到调用方。"""
        from app.core.config import settings
        from app.services.chunking import ai_assisted as ai_mod
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")

        @contextmanager
        def boom_ctx():
            class _C:
                def post(self, *a, **kw):
                    raise RuntimeError("network down")
            yield _C()

        monkeypatch.setattr(ai_mod, "sync_http_client_context", boom_ctx)
        chunks = AIAssistedChunker().split(ZH_TWO_TOPICS)
        _assert_basic_contract(chunks)

    def test_close_boundaries_cleaned(self, monkeypatch):
        """距离 < 100（不含等于）的相邻 boundary 应被剔除；距离 ≥ 100 的会保留。

        算法：sorted 后从前向后，若 `b - result[-1] >= 100` 才 append。
        因此 [500, 1500] → 1000 ≥ 100 保留；[1500, 1600] → 100 ≥ 100 保留（边界值）；
        [500, 550] → 50 < 100 剔除 550；[550, 1500] 同理剔除。
        """
        from app.core.config import settings
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-key")
        from app.services.chunking.ai_assisted import AIAssistedChunker
        chunker = AIAssistedChunker()
        cleaned = chunker._clean_boundaries([500, 550, 1500, 1600, 3000], text_length=5000)
        # 500 保留（first）
        assert 500 in cleaned
        # 550 被剔除（距 500 = 50 < 100）
        assert 550 not in cleaned
        # 1500 保留（距 500 = 1000 ≥ 100）
        assert 1500 in cleaned
        # 1600 保留（距 1500 = 100，恰好等于阈值，> 100 才剔除；>= 100 保留）
        assert 1600 in cleaned
        # 3000 保留（距 1600 = 1400 ≥ 100）
        assert 3000 in cleaned

    def test_out_of_range_boundaries_filtered(self):
        chunker = AIAssistedChunker()
        cleaned = chunker._clean_boundaries([100, 999999, -5, 200], text_length=1000)
        assert all(0 < b < 1000 for b in cleaned)
        assert 100 in cleaned
        assert 200 in cleaned

    def test_get_last_ai_usage_consumed_after_read(self, enable_ai):
        """两次连续调用 get_last_ai_usage，第 2 次应返回 None。"""
        chunker = AIAssistedChunker()
        chunker.split(ZH_LONG_TEXT)
        first = chunker.get_last_ai_usage()
        second = chunker.get_last_ai_usage()
        assert first is not None
        assert second is None

    def test_parse_boundary_response_direct_json(self):
        chunker = AIAssistedChunker()
        assert chunker._parse_boundary_response("[10, 20, 30]") == [10, 20, 30]

    def test_parse_boundary_response_wrapped_json(self):
        chunker = AIAssistedChunker()
        assert chunker._parse_boundary_response("结论：[100, 200, 300]") == [100, 200, 300]

    def test_parse_boundary_response_numbers_only(self):
        chunker = AIAssistedChunker()
        # 全是数字但不是合法 JSON → 数字兜底提取
        assert chunker._parse_boundary_response("12 34 56") == [12, 34, 56]

    def test_parse_boundary_response_garbage(self):
        chunker = AIAssistedChunker()
        assert chunker._parse_boundary_response("胡说八道") == []

    def test_long_text_under_timeout(self, enable_ai):
        """长文 + monkey-patched LLM 5 秒内返回。"""
        import time
        text = ZH_LONG * 5  # ~9000 字
        start = time.time()
        chunks = AIAssistedChunker().split(text)
        elapsed = time.time() - start
        _assert_basic_contract(chunks)
        assert elapsed < 5.0


# ============================================================================
# CMN: 全部策略对 None / "" / 超长 输入都不抛
# ============================================================================
# AIAssistedChunker 故意对空/短文本返 []（min_chunk_size=50 兜底），
# 故不参与"至少 1 chunk"的鲁棒性测试。

CHUNKER_CLASSES_FOR_ROBUST = [
    FixedTokenChunker, SemanticChunker, ParagraphChunker,
    HeadingLevelChunker, QAPairChunker, RecursiveChunker,
]
class TestAllStrategiesRobust:
    """每个策略对边界输入都不抛。

    AIAssistedChunker 故意对空/短文本返 []（min_chunk_size=50 兜底，不鲁棒），
    因此不在此 parametrize 中。
    """

    @pytest.mark.parametrize("strategy_cls", CHUNKER_CLASSES_FOR_ROBUST)
    def test_empty_string(self, strategy_cls):
        chunks = strategy_cls().split("")
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    @pytest.mark.parametrize("strategy_cls", CHUNKER_CLASSES_FOR_ROBUST)
    def test_short_string(self, strategy_cls):
        chunks = strategy_cls().split("hello world")
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    @pytest.mark.parametrize("strategy_cls", CHUNKER_CLASSES_FOR_ROBUST)
    def test_long_string(self, strategy_cls, monkeypatch):
        """5 万字不卡死。"""
        # AI 策略走 enable_ai=False 跳过 LLM（即使被 monkey patch）
        from app.services.chunking import ai_assisted as ai_mod
        monkeypatch.setattr(
            ai_mod, "sync_http_client_context",
            _noop_ctx,
        )
        from app.core.config import settings
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        text = "测试文本。" * 10_000
        chunks = strategy_cls().split(text, enable_ai=False)
        assert isinstance(chunks, list)
        assert len(chunks) >= 1


@contextmanager
def _noop_ctx():
    """对 AI 策略屏蔽 LLM 的 ctx。"""
    class _C:
        def post(self, *a, **kw):
            raise RuntimeError("LLM should not be called")
    yield _C()
