#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不同文档切片对比 Demo
====================
对 samples/ 下多种格式的样例文档，分别用 7 种切片策略进行切片，
生成一份可视化对比报告 docs/不同文档切片对比报告.html。

AI 辅助策略使用「模拟 LLM」（离线，不调用真实 DeepSeek），
仅用于演示边界检测流程，报告内已明确标注。

运行: python backend/scripts/slice_demo.py   (无需外部网络/密钥)
"""
import os
import sys
import re
import html as _html

# 让 `app` 可被导入（无论当前工作目录）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.chunking.fixed_token import FixedTokenChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.chunking.paragraph import ParagraphChunker
from app.services.chunking.heading_level import HeadingLevelChunker
from app.services.chunking.qa_pair import QAPairChunker
from app.services.chunking.recursive import RecursiveChunker
from app.services.chunking.ai_assisted import AIAssistedChunker
from app.core.config import settings

# ---- 路径 ----
REPO_ROOT = os.path.dirname(BACKEND_DIR)
SAMPLES_DIR = os.path.join(REPO_ROOT, "samples")
OUTPUT_HTML = os.path.join(REPO_ROOT, "docs", "不同文档切片对比报告.html")

# 让 AI 策略走「模拟 LLM」分支（离线演示）
settings.DEEPSEEK_API_KEY = "fake-demo-key"


# ---- 模拟 LLM：直接替换边界检测方法为离线计算 ----
def _fake_detect_boundaries(self, text, paragraphs, temperature):
    total = len(text)
    if total <= 1:
        return []
    cum = 0
    offsets = []
    for p in paragraphs:
        cum += len(p) + 1
        offsets.append(cum)
    bounds = []
    for t in (total // 3, 2 * total // 3):
        if not offsets:
            break
        near = min(offsets, key=lambda o: abs(o - t))
        if near not in bounds:
            bounds.append(near)
    # 记录 token 用量（被 get_last_ai_usage 读取）
    self._last_ai_usage = {
        "input_tokens": total // 2,
        "output_tokens": 12,
        "estimated_cost": 0.00012,
    }
    return sorted(bounds)


AIAssistedChunker._detect_boundaries_with_llm = _fake_detect_boundaries

# ---- 策略注册（含演示用参数）----
STRATEGIES = [
    ("fixed_token", "固定Token", FixedTokenChunker,
     {"chunk_size": 300, "overlap": 50}),
    ("semantic", "语义切块", SemanticChunker,
     {"similarity_threshold": 0.5, "max_chunk_size": 800, "min_chunk_size": 100}),
    ("paragraph", "段落切块", ParagraphChunker,
     {"max_paragraph_size": 600, "merge_small": True, "merge_threshold": 200}),
    ("heading_level", "标题层级", HeadingLevelChunker,
     {"min_section_size": 50, "include_title_in_content": True}),
    ("qa_pair", "问答对", QAPairChunker,
     {"min_chunk_size": 20, "max_chunk_size": 2000, "include_q_prefix": True, "include_a_prefix": True}),
    ("recursive", "递归切片", RecursiveChunker,
     {"max_chunk_size": 400, "min_chunk_size": 50, "overlap_sentences": 1}),
    ("ai_assisted", "AI辅助(模拟)", AIAssistedChunker,
     {"max_chunk_size": 800, "min_chunk_size": 50, "enable_ai": True}),
]


# ---- 文档加载（按格式抽取纯文本）----
def load_doc(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    if ext == ".html":
        # 把 <h1>..</h1> 转成 Markdown 标题，便于「标题层级」策略识别；其余标签剥离
        text = raw
        text = re.sub(r"<(h[1-6])>", r"\n\n<\1>", text, flags=re.I)
        text = re.sub(r"</(h[1-6])>", r"</\1>\n\n", text, flags=re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text, "HTML"
    if ext == ".csv":
        import csv
        rows = list(csv.reader(raw.splitlines()))
        out = []
        for r in rows:
            if len(r) >= 2 and r[0].strip() and r[1].strip():
                out.append(f"问：{r[0].strip()}\n答：{r[1].strip()}")
        return "\n\n".join(out), "CSV(问答)"
    fmt = "Markdown" if ext == ".md" else "纯文本"
    return raw, fmt


# ---- 主流程 ----
def run():
    docs = sorted(
        p for p in os.listdir(SAMPLES_DIR)
        if p.lower().endswith((".md", ".txt", ".html", ".csv")) and not p.startswith(".")
    )
    report = []
    for doc_name in docs:
        path = os.path.join(SAMPLES_DIR, doc_name)
        text, fmt = load_doc(path)
        char_count = len(text)
        para_count = len([x for x in re.split(r"\n\s*\n", text) if x.strip()])
        print(f"[文档] {doc_name} ({fmt}) 字符={char_count} 段落≈{para_count}")
        doc_rows = []
        for key, label, cls, params in STRATEGIES:
            chunker = cls()
            if key == "ai_assisted":
                chunks = chunker.split(text, **params)
                usage = chunker.get_last_ai_usage()  # 同一实例读取用量
            else:
                chunks = chunker.split(text, **params)
                usage = None
            sizes = [len(c.content) for c in chunks] or [0]
            avg = sum(sizes) / len(sizes)
            doc_rows.append({
                "key": key, "label": label,
                "count": len(chunks),
                "avg": round(avg), "mx": max(sizes), "mn": min(sizes),
                "first": chunks[0].content[:60] if chunks else "",
                "chunks": chunks,
                "usage": usage,
            })
            print(f"    - {label}: {len(chunks)} 块, 平均 {avg:.0f} 字")
        report.append({
            "name": doc_name, "fmt": fmt,
            "char_count": char_count, "para_count": para_count,
            "rows": doc_rows,
        })
    render_html(report)
    print(f"\n报告已生成: {OUTPUT_HTML}")


def render_html(report):
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>不同文档切片对比报告</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2329;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--accent2:#0e9f6e;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:24px;margin:0 0 6px}
.sub{color:var(--muted);font-size:14px;margin-bottom:24px}
.doc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:26px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.doc h2{font-size:18px;margin:0 0 4px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{font-size:12px;font-weight:600;color:#fff;background:var(--accent);padding:2px 9px;border-radius:999px}
.meta{color:var(--muted);font-size:13px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:10px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;background:#fafbfc}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.preview{color:var(--muted);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
details{border:1px solid var(--line);border-radius:8px;margin:8px 0;padding:0 12px;background:#fcfcfd}
summary{cursor:pointer;padding:8px 0;font-weight:600;font-size:13px}
.chunk{border-top:1px dashed var(--line);padding:8px 0;font-size:12.5px}
.chunk .ix{color:var(--accent2);font-weight:700;margin-right:6px}
.chunk .ct{color:var(--muted)}
.note{font-size:12px;color:var(--muted);margin-top:6px}
</style></head><body><div class="wrap">
<h1>不同文档切片对比报告</h1>
<div class="sub">对多种格式样例文档，分别用 7 种切片策略进行切片并对比块数 / 长度 / 内容预览。AI 辅助策略使用<b>模拟 LLM</b>（离线，不调用真实 DeepSeek）。</div>
""")
    for d in report:
        parts.append(f'<div class="doc"><h2>{_html.escape(d["name"])} '
                     f'<span class="badge">{_html.escape(d["fmt"])}</span></h2>')
        parts.append(f'<div class="meta">字符数 {d["char_count"]} · 段落数约 {d["para_count"]}</div>')
        parts.append('<table><thead><tr>'
                     '<th>策略</th><th class="num">块数</th><th class="num">平均长度</th>'
                     '<th class="num">最大块</th><th class="num">最小块</th><th>首块预览</th>'
                     '</tr></thead><tbody>')
        for r in d["rows"]:
            parts.append(
                f'<tr><td><b>{_html.escape(r["label"])}</b></td>'
                f'<td class="num">{r["count"]}</td>'
                f'<td class="num">{r["avg"]}</td>'
                f'<td class="num">{r["mx"]}</td>'
                f'<td class="num">{r["mn"]}</td>'
                f'<td class="preview" title="{_html.escape(r["first"])}">{_html.escape(r["first"])}</td></tr>'
            )
        parts.append('</tbody></table>')
        for r in d["rows"]:
            usage_txt = ""
            if r["usage"]:
                u = r["usage"]
                usage_txt = (f' · 模拟LLM 用量: {u["input_tokens"]} in / {u["output_tokens"]} out · '
                             f'¥{u["estimated_cost"]}')
            parts.append(f'<details><summary>{_html.escape(r["label"])} — {r["count"]} 块{usage_txt}</summary>')
            if not r["chunks"]:
                parts.append('<div class="note">无切片结果（文本过短或被过滤）。</div>')
            for c in r["chunks"]:
                content = c.content[:300] + ("…" if len(c.content) > 300 else "")
                meta = " · ".join(f"{k}={v}" for k, v in c.metadata.items()
                                  if k not in ("strategy",))
                parts.append(
                    f'<div class="chunk"><span class="ix">#{c.index}</span>'
                    f'<span class="ct">[{len(c.content)}字{meta and " · " + meta}]</span><br>'
                    f'{_html.escape(content)}</div>'
                )
            parts.append('</details>')
        parts.append('</div>')
    parts.append('</div></body></html>')
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


if __name__ == "__main__":
    run()
