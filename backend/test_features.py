"""
功能测试脚本 - 验证新增的RAG功能
运行方式: cd backend && python test_features.py
"""
from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, ".")


async def test_query_rewrite():
    """测试查询改写功能"""
    print("\n=== 测试查询改写功能 ===")
    try:
        from app.services.query_rewrite import rewrite_query, expand_query_for_search

        # 测试1: 基本查询改写
        result = await rewrite_query("那XX呢？")
        print(f"原始查询: 那XX呢？")
        print(f"改写结果: {result['rewritten_query']}")
        print(f"查询变体: {result['query_variants']}")
        print(f"改写说明: {result['analysis']}")

        # 测试2: 查询扩展
        queries = await expand_query_for_search("如何配置数据库连接？")
        print(f"\n查询扩展结果: {queries}")

        print("✓ 查询改写功能正常")
        return True
    except Exception as e:
        print(f"✗ 查询改写功能异常: {e}")
        return False


async def test_rerank():
    """测试Rerank重排序功能"""
    print("\n=== 测试Rerank重排序功能 ===")
    try:
        from app.services.rerank_service import rerank_results, cross_encoder_similarity

        # 测试1: 启发式评分
        score1 = cross_encoder_similarity("数据库配置", "MySQL数据库连接配置方法")
        score2 = cross_encoder_similarity("数据库配置", "今天天气很好")
        print(f"相关文档评分: {score1}")
        print(f"不相关文档评分: {score2}")

        # 测试2: LLM Rerank
        test_docs = [
            {"chunk_id": 1, "content": "MySQL数据库连接配置需要设置host、port、user、password"},
            {"chunk_id": 2, "content": "Python是一种编程语言"},
            {"chunk_id": 3, "content": "数据库连接池可以提高性能"},
        ]
        reranked = await rerank_results("如何配置数据库连接？", test_docs, top_k=2, use_llm=True)
        print(f"\nRerank结果:")
        for doc in reranked:
            print(f"  - 分数: {doc.get('rerank_score', 'N/A')}, 内容: {doc['content'][:50]}...")

        print("✓ Rerank重排序功能正常")
        return True
    except Exception as e:
        print(f"✗ Rerank重排序功能异常: {e}")
        return False


async def test_hybrid_search():
    """测试混合检索功能"""
    print("\n=== 测试混合检索功能 ===")
    try:
        from app.services.hybrid_search import reciprocal_rank_fusion, BM25

        # 测试1: RRF融合算法
        list1 = [
            {"chunk_id": 1, "content": "文档1", "score": 0.9},
            {"chunk_id": 2, "content": "文档2", "score": 0.8},
            {"chunk_id": 3, "content": "文档3", "score": 0.7},
        ]
        list2 = [
            {"chunk_id": 2, "content": "文档2", "score": 0.95},
            {"chunk_id": 4, "content": "文档4", "score": 0.85},
            {"chunk_id": 1, "content": "文档1", "score": 0.75},
        ]

        fused = reciprocal_rank_fusion([list1, list2])
        print("RRF融合结果:")
        for r in fused[:3]:
            print(f"  - Chunk ID: {r['chunk_id']}, RRF分数: {r['rrf_score']}")

        # 测试2: BM25评分
        bm25 = BM25()
        query_tokens = ["数据库", "配置"]
        doc_tokens = ["MySQL", "数据库", "连接", "配置", "方法"]
        doc_freq = {"数据库": 5, "配置": 3}
        score = bm25.score(query_tokens, doc_tokens, doc_freq, 100)
        print(f"\nBM25评分: {score}")

        print("✓ 混合检索功能正常")
        return True
    except Exception as e:
        print(f"✗ 混合检索功能异常: {e}")
        return False


async def test_document_parser():
    """测试文档智能解析功能"""
    print("\n=== 测试文档智能解析功能 ===")
    try:
        from app.services.document_parser import (
            extract_code_blocks,
            extract_formulas,
            _table_to_markdown,
        )

        # 测试1: 代码块提取
        md_text = """
这是一段文本。

```python
def hello():
    print("Hello World")
```

这是另一段文本。

```sql
SELECT * FROM users WHERE id = 1
```
"""
        code_blocks = extract_code_blocks(md_text)
        print(f"提取到 {len(code_blocks)} 个代码块:")
        for block in code_blocks:
            print(f"  - 语言: {block['language']}, 内容: {block['content'][:30]}...")

        # 测试2: 公式提取
        formula_text = "这是一个行内公式 $E = mc^2$ 和显示公式 $$\\int_0^\\infty e^{-x} dx = 1$$"
        formulas = extract_formulas(formula_text)
        print(f"\n提取到 {len(formulas)} 个公式:")
        for f in formulas:
            print(f"  - 类型: {f['type']}, 内容: {f['content']}")

        # 测试3: 表格转Markdown
        table_data = [
            ["姓名", "年龄", "城市"],
            ["张三", "25", "北京"],
            ["李四", "30", "上海"],
        ]
        markdown = _table_to_markdown(table_data)
        print(f"\n表格转Markdown:\n{markdown}")

        print("✓ 文档智能解析功能正常")
        return True
    except Exception as e:
        print(f"✗ 文档智能解析功能异常: {e}")
        return False


async def test_embedding_service():
    """测试Embedding服务"""
    print("\n=== 测试Embedding服务 ===")
    try:
        from app.services.embedding_service import embed_single_text, estimate_token_count

        # 测试1: Token估算
        text1 = "这是一个中文测试"
        text2 = "This is an English test"
        tokens1 = estimate_token_count(text1)
        tokens2 = estimate_token_count(text2)
        print(f"中文文本Token估算: {tokens1}")
        print(f"英文文本Token估算: {tokens2}")

        # 测试2: Embedding (需要API Key)
        from app.core.config import settings
        if settings.TONGYI_API_KEY:
            vector, tokens = await embed_single_text("测试向量化")
            print(f"\n向量维度: {len(vector)}")
            print(f"Token消耗: {tokens}")
            print("✓ Embedding服务正常")
        else:
            print("⚠ 未配置TONGYI_API_KEY，跳过Embedding测试")

        return True
    except Exception as e:
        print(f"✗ Embedding服务异常: {e}")
        return False


async def main():
    """运行所有测试"""
    print("=" * 50)
    print("RAG系统功能测试")
    print("=" * 50)

    results = {}

    # 运行所有测试
    results["查询改写"] = await test_query_rewrite()
    results["Rerank重排序"] = await test_rerank()
    results["混合检索"] = await test_hybrid_search()
    results["文档智能解析"] = await test_document_parser()
    results["Embedding服务"] = await test_embedding_service()

    # 汇总结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    passed = sum(results.values())
    total = len(results)

    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
