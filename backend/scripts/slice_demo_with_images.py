"""
图文混排切片对比演示（路线 B：OCR 文本化）。

对含图片的 Markdown / HTML 样例文档，分别用：
  - 旧行为：parse_document_intelligently(ocr_backend=None)  —— 图片被当纯文本残留/丢弃
  - 新行为：parse_document_intelligently(ocr_backend=mock) —— 图片经 OCR 文字回填进文本流
然后各跑 7 种切片策略，对比图片文字是否进入 chunk。

运行：
  cd backend
  PYTHONPATH=. ./venv/Scripts/python.exe scripts/slice_demo_with_images.py
"""
from __future__ import annotations

import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend

from app.core.config import settings
from app.services.chunking.ai_assisted import AIAssistedChunker
from app.services.chunking.fixed_token import FixedTokenChunker
from app.services.chunking.heading_level import HeadingLevelChunker
from app.services.chunking.paragraph import ParagraphChunker
from app.services.chunking.qa_pair import QAPairChunker
from app.services.chunking.recursive import RecursiveChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.document_parser import (
    format_structured_content,
    parse_document_intelligently,
)
from app.services.ocr_service import get_ocr_backend

# AI 策略离线模拟（不依赖 DeepSeek key）
settings.DEEPSEEK_API_KEY = "fake"
import app.services.chunking.ai_assisted as ai_mod


def _fake_boundaries(self, text, params, tmp):
    self._last_ai_usage = {
        "input_tokens": 100,
        "output_tokens": 5,
        "estimated_cost": 0.0001,
    }
    L = len(text)
    return [L // 3, 2 * L // 3]


ai_mod.AIAssistedChunker._detect_boundaries_with_llm = _fake_boundaries

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES_DIR = os.path.join(BASE, "samples_with_images")

STRATEGIES = [
    ("固定Token", FixedTokenChunker, {"chunk_size": 200, "overlap": 40}),
    ("语义切块", SemanticChunker, {}),
    ("段落切块", ParagraphChunker, {"max_paragraph_size": 300}),
    ("标题层级", HeadingLevelChunker, {}),
    ("问答对", QAPairChunker, {}),
    ("递归切片", RecursiveChunker, {}),
    ("AI辅助(模拟)", AIAssistedChunker, {"max_chunk_size": 300, "min_chunk_size": 50, "enable_ai": True}),
]

SAMPLES = [
    ("产品说明.md", "md"),
    ("帮助页面.html", "html"),
]


def run_slice(text, cls, params):
    try:
        return cls().split(text, **params), None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def snippet(s: str, n: int = 220) -> str:
    s = s.strip()
    return s[:n] + ("…" if len(s) > n else "")


def build_report(rows, docs_meta):
    out = []
    style = """
    <style>
      body{font-family:-apple-system,'Segoe UI',sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222;line-height:1.6;background:#fff}
      h1{color:#1a3c6e}h2{color:#1a3c6e;border-bottom:2px solid #e3e8f0;padding-bottom:6px;margin-top:34px}
      .meta{color:#666;font-size:14px;background:#f5f8fc;padding:12px 16px;border-radius:8px;border:1px solid #e3e8f0}
      table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
      th,td{border:1px solid #d8dee9;padding:8px 10px;text-align:left;vertical-align:top}
      th{background:#eef3fb}
      .old{color:#b00}.new{color:#087a2e}
      .hit-yes{color:#087a2e;font-weight:600}.hit-no{color:#888}
      .code{background:#f6f8fa;border:1px solid #e3e8f0;border-radius:6px;padding:10px 12px;
             white-space:pre-wrap;word-break:break-all;font-family:Consolas,Menlo,monospace;font-size:12.5px;max-height:160px;overflow:auto}
      .tag-old{background:#fdecea;color:#b00;padding:1px 6px;border-radius:4px;font-size:12px}
      .tag-new{background:#e7f6ec;color:#087a2e;padding:1px 6px;border-radius:4px;font-size:12px}
      .note{color:#666;font-size:13px}
    </style>"""
    out.append("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>")
    out.append("<title>图文混排切片对比报告（OCR 文本化）</title>")
    out.append(style)
    out.append("</head><body>")
    out.append("<h1>图文混排切片对比报告</h1>")
    out.append("<div class='meta'>")
    out.append(
        "路线 <b>B. OCR 文本化</b> 演示：对含图片的 Markdown / HTML 文档，"
        "对比 <span class='tag-old'>旧行为（无 OCR，图片被当纯文本/被丢弃）</span> 与 "
        "<span class='tag-new'>新行为（图片经 mock OCR 文字回填进文本流）</span> "
        "在 7 种切片策略下的差异。OCR 后端当前为 <b>mock</b>（读图片尺寸返回模拟识别文字），"
        "接入真实引擎（通义 qwen-vl / 本地 rapidocr）只需替换 <code>get_ocr_backend()</code> 的参数。"
    )
    out.append("</div>")

    for doc in docs_meta:
        fname = doc["fname"]
        out.append(f"<h2>文档：{html.escape(fname)}（{doc['ftype']}）</h2>")
        out.append(
            f"<p class='note'>图片总数：<b>{doc['img_count']}</b> · "
            f"成功 OCR 命中：<b>{doc['ocr_hit']}</b></p>"
        )
        # 文本对比
        out.append("<h3>解析后文本对比（图片如何处理）</h3>")
        out.append("<p class='tag-old'>旧（无 OCR）</p>")
        out.append(f"<div class='code'>{html.escape(snippet(doc['old_text'], 400))}</div>")
        out.append("<p class='tag-new'>新（mock OCR 回填）</p>")
        out.append(f"<div class='code'>{html.escape(snippet(doc['new_text'], 400))}</div>")

        # 策略对比表
        out.append("<h3>7 种策略切片对比</h3>")
        out.append(
            "<table><tr><th>策略</th><th>旧 chunk 数</th><th>新 chunk 数</th>"
            "<th>新切片命中图片文字</th><th>说明</th></tr>"
        )
        for r in rows:
            if r["doc"] != fname:
                continue
            hit_cls = "hit-yes" if r["hit"] else "hit-no"
            hit_txt = "✅ 是" if r["hit"] else "— 否"
            out.append(
                f"<tr><td>{html.escape(r['strategy'])}</td>"
                f"<td class='old'>{r['old_n']}</td>"
                f"<td class='new'>{r['new_n']}</td>"
                f"<td class='{hit_cls}'>{hit_txt}</td>"
                f"<td class='note'>{html.escape(r['note'])}</td></tr>"
            )
        out.append("</table>")

        # 展示新切片中第一个含图片 OCR 文字的 chunk
        if doc.get("sample_chunk"):
            out.append("<h3>新切片中图片文字落点示例</h3>")
            out.append(
                f"<div class='code'>{html.escape(snippet(doc['sample_chunk'], 400))}</div>"
            )

    out.append("<h2>结论</h2>")
    out.append(
        "<ul>"
        "<li><b>旧行为</b>：Markdown 的 <code>![](path)</code> 作为纯文本残留在 chunk 中，"
        "可能被固定Token/语义策略从中间切断；HTML 的 <code>&lt;img&gt;</code> 被 "
        "<code>get_text()</code> 直接丢弃，图片信息完全消失；DOCX 图片仅记文件名、不进 chunk。</li>"
        "<li><b>新行为（OCR 文本化）</b>：图片被提取并经 OCR 转成文字，回填进文本流"
        "（<code>[图片OCR 开始]…[图片OCR 结束]</code>），7 种策略都能把它当正文切片，"
        "图片里的文字因此可被检索与问答。</li>"
        "<li><b>切换真实引擎</b>：把 <code>get_ocr_backend('mock')</code> 改为 "
        "<code>get_ocr_backend('tongyi-vl')</code>（需 TONGYI_API_KEY）或 "
        "<code>'rapidocr'</code>（需 pip 安装），无需改动 parser 与切片主链路。</li>"
        "</ul>"
    )
    out.append("</body></html>")
    return "\n".join(out)


def main():
    rows = []
    docs_meta = []
    for fname, ftype in SAMPLES:
        path = os.path.join(SAMPLES_DIR, fname)
        old_parsed = parse_document_intelligently(path, ftype)  # 无 OCR
        old_text = format_structured_content(old_parsed)

        ocr = get_ocr_backend("mock")
        new_parsed = parse_document_intelligently(path, ftype, ocr_backend=ocr)
        new_text = format_structured_content(new_parsed)

        img_count = len(new_parsed.get("images", []))
        ocr_hit = sum(1 for im in new_parsed.get("images", []) if im.get("ocr_text"))

        sample_chunk = ""
        for sname, cls, params in STRATEGIES:
            old_chunks, old_err = run_slice(old_text, cls, params)
            new_chunks, new_err = run_slice(new_text, cls, params)
            hit = any("[图片OCR" in c.content for c in new_chunks)
            note = ""
            if new_err:
                note = f"新切片异常: {new_err}"
            elif old_err:
                note = f"旧切片异常: {old_err}"
            elif sname == "问答对":
                note = "图片非问答格式，问答策略不产生额外图片块（图片文字仍在文本流中）"
            if not sample_chunk:
                sample_chunk = next(
                    (c.content for c in new_chunks if "[图片OCR" in c.content), ""
                )
            rows.append(
                {
                    "doc": fname,
                    "strategy": sname,
                    "old_n": len(old_chunks),
                    "new_n": len(new_chunks),
                    "hit": hit,
                    "note": note,
                }
            )
        docs_meta.append(
            {
                "fname": fname,
                "ftype": ftype,
                "img_count": img_count,
                "ocr_hit": ocr_hit,
                "old_text": old_text,
                "new_text": new_text,
                "sample_chunk": sample_chunk,
            }
        )

    report = build_report(rows, docs_meta)
    docs_dir = os.path.join(BASE, "..", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, "图文混排切片对比报告.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已生成: {out_path}")
    for d in docs_meta:
        print(f"  {d['fname']}: 图片 {d['img_count']} / OCR命中 {d['ocr_hit']}")


if __name__ == "__main__":
    main()
