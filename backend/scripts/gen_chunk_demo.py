"""
生成「七种切分策略演示」HTML —— 真实跑通 backend 的 7 个 chunking 策略，
用同一段混合样例文本切片，输出浅底、纯中文、自包含 HTML 到 docs/。

运行：cd backend && PYTHONPATH=. ./venv/Scripts/python.exe scripts/gen_chunk_demo.py
"""
import os
import sys
import html
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("demo")

# ---- 让 app 包可 import（cwd=backend，sys.path 默认含 cwd）----
from app.services.chunking.fixed_token import FixedTokenChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.chunking.paragraph import ParagraphChunker
from app.services.chunking.heading_level import HeadingLevelChunker
from app.services.chunking.qa_pair import QAPairChunker
from app.services.chunking.recursive import RecursiveChunker
from app.services.chunking.ai_assisted import AIAssistedChunker
from app.services.chunking.base import ChunkResult

# ----------------------------------------------------------------------------
# 同一份混合样例文本：含 H1/H2 标题、段落、FAQ 问答、日志行，用来体现 7 策略差异
# ----------------------------------------------------------------------------
SAMPLE = """# 智能音箱 SoundFree X1 使用手册

## 一、开箱与连接

将音箱接通电源，指示灯亮起蓝色呼吸灯表示开机。打开手机蓝牙，在可用设备列表中选择"SoundFree X1"完成配对。首次使用建议先通过 App 升级至最新固件，以获得更稳定的连接体验与更完整的语音技能。

如果搜索不到设备，请长按电源键 5 秒进入配对模式，指示灯快闪后重试。连接成功后会有语音提示"蓝牙已连接"，此时即可开始使用语音助手功能。

## 二、防水与佩戴

本设备支持 IPX8 级防水，可在游泳、淋浴等水下场景佩戴，但不建议在桑拿、热水浴等高温高湿环境使用。耳塞提供 S/M/L 三种尺寸，建议选择贴合耳道的一款以获得更好音质与主动降噪效果。

日常清洁请用软布擦拭，避免消毒液直接喷洒机身。充电触点如遇氧化可用橡皮轻擦恢复导电性。请勿使用酒精湿巾长期擦拭，以免腐蚀外壳涂层。

## 三、续航与充电

单次充满电约可使用 8 小时，配合充电盒总续航可达 32 小时。充电盒支持 Type-C 快充，充电 10 分钟可使用约 2 小时。低电量时音箱会语音提醒"电量不足"，此时请及时放入充电盒。

长期不使用时，建议保持电量在 50% 左右存放，避免完全放电损伤电芯。每三个月至少充放电一次以维持电池健康度。

## 四、常见问题

问：耳机可以游泳时佩戴吗？
答：可以。设备具备 IPX8 防水等级，适合游泳、淋浴等水上活动，但不建议用于桑拿等高温环境。

问：续航时间多久？
答：单次充电约 8 小时，配合充电盒总续航 32 小时，支持 Type-C 快充，充电 10 分钟可用约 2 小时。

问：搜索不到蓝牙怎么办？
答：长按电源键 5 秒进入配对模式，指示灯快闪后在手机蓝牙列表重试即可完成连接。

问：如何重置设备？
答：同时长按电源键和音量键 10 秒，直到红灯常亮后松开，即可恢复出厂设置。

## 五、故障排查日志

[INFO] 2026-08-25 09:12 boot complete, firmware v2.3.1
[INFO] 2026-08-25 09:12 bluetooth module init ok
[WARN] 2026-08-25 09:13 pairing timeout, retry attempt 1
[ERROR] 2026-08-25 09:14 auth failed, check pin code
[INFO] 2026-08-25 09:15 paired success, device online
[WARN] 2026-08-25 09:20 low battery 15%, remind user
[INFO] 2026-08-25 09:35 firmware check, already latest
[ERROR] 2026-08-25 10:01 network lost, reconnecting
[INFO] 2026-08-25 10:02 network restored, sync ok

## 六、语音指令示例

"播放周杰伦的歌" —— 调用音乐技能播放指定歌手歌曲。
"今天天气怎么样" —— 查询当前城市天气并语音播报。
"设置一个明天早上七点的闹钟" —— 创建定时提醒。
"帮我查一下快递到哪了" —— 联动物流查询技能返回进度。
""".strip()

# ----------------------------------------------------------------------------
# 7 个策略：中文名 / 注册名 / 实例 / 适用文档 / 业务描述 / 费用维度
# ----------------------------------------------------------------------------
STRATEGIES = [
    ("固定Token", "fixed_token", FixedTokenChunker(),
     "适配通用文档，可自定义块大小、重叠长度，保证检索连贯性",
     "通用文档 / 未知类型", "无额外费用"),
    ("语义切块", "semantic", SemanticChunker(),
     "基于语义边界智能拆分，避免完整语义断裂",
     "长文 / 专业文档", "无额外费用"),
    ("段落切块", "paragraph", ParagraphChunker(),
     "按自然段落、空行分隔",
     "笔记 / Markdown / 普通文稿", "无额外费用"),
    ("标题层级", "heading_level", HeadingLevelChunker(),
     "识别一二三级标题，按章节拆分，保留文档层级结构",
     "手册 / 规范 / 书籍类文档", "无额外费用"),
    ("问答对", "qa_pair", QAPairChunker(),
     "自动提取文档内问答结构化内容，生成独立问答文本块",
     "FAQ / 题库 / 售后问答手册", "无额外费用"),
    ("递归切片", "recursive", RecursiveChunker(),
     "多层递进式分层切割，超长片段二次分割，最小化语义破碎，无额外 API 消耗",
     "超大纯文本 / 日志文件", "无额外费用"),
    ("AI辅助", "ai_assisted", AIAssistedChunker(),
     "调用大模型理解全文逻辑自主划分片段，自动合并关联内容、修正破碎短句",
     "格式杂乱无规则杂合文档", "产生 LLM Token 费用"),
]

PREVIEW = 170  # 每块预览字符数


def run_one(cn, en, inst, desc, suit, cost):
    meta = {
        "cn": cn, "en": en, "desc": desc, "suit": suit, "cost": cost,
        "defaults": inst.get_default_params(),
        "count": 0, "chunks": [], "note": "",
    }
    try:
        chunks = inst.split(SAMPLE)
    except Exception as e:  # 极端兜底
        chunks = [ChunkResult(index=0, content=SAMPLE, token_count=len(SAMPLE) // 2)]
        meta["note"] = f"运行异常已回退整段：{e}"
    meta["count"] = len(chunks)
    for c in chunks:
        txt = c.content if isinstance(c.content, str) else str(c.content)
        meta["chunks"].append({
            "idx": c.index,
            "tokens": c.token_count,
            "chars": len(txt),
            "preview": txt[:PREVIEW] + ("…" if len(txt) > PREVIEW else ""),
            "meta": c.metadata,
        })
    # AI 策略在无 API key 时 fallback
    if en == "ai_assisted":
        used = any(bool(ch.get("ai_used")) for ch in [c.metadata for c in chunks])
        meta["note"] = ("无 DEEPSEEK_API_KEY，已自动 fallback 到段落切分（不消耗 Token）；"
                        "配置密钥后会调用大模型智能分段。")
    return meta


def esc(s):
    return html.escape(str(s))


def params_html(p):
    return " · ".join(f"<code>{esc(k)}={esc(v)}</code>" for k, v in p.items())


def chunk_card(ch):
    meta_str = " · ".join(f"{esc(k)}={esc(v)}" for k, v in ch["meta"].items())
    return f"""
      <div class="ck">
        <div class="ck-h">块 #{ch['idx']} <span class="ck-m">{ch['chars']} 字 / {ch['tokens']} tok</span></div>
        <div class="ck-body">{esc(ch['preview'])}</div>
        <div class="ck-meta">{meta_str}</div>
      </div>"""


def strategy_section(m):
    cost_cls = "cost-free" if m["cost"].startswith("无") else "cost-paid"
    cards = "\n".join(chunk_card(c) for c in m["chunks"])
    note = f'<div class="note">⚠️ {esc(m["note"])}</div>' if m["note"] else ""
    return f"""
  <section class="strat">
    <div class="s-head">
      <div class="s-title"><span class="badge">{esc(m['en'])}</span> {esc(m['cn'])}</div>
      <div class="s-count">切片 {m['count']} 块</div>
    </div>
    <div class="s-row">
      <div class="s-cell"><b>适用文档</b><br/>{esc(m['suit'])}</div>
      <div class="s-cell"><b>业务描述</b><br/>{esc(m['desc'])}</div>
      <div class="s-cell"><b>默认参数</b><br/>{params_html(m['defaults'])}</div>
      <div class="s-cell"><b>费用</b><br/><span class="{cost_cls}">{esc(m['cost'])}</span></div>
    </div>
    <div class="chunks">{cards}</div>
    {note}
  </section>"""


def build_html(results):
    sections = "\n".join(strategy_section(m) for m in results)
    overview = "\n".join(
        f'<tr><td>{esc(m["cn"])}</td><td><code>{esc(m["en"])}</code></td>'
        f'<td>{esc(m["suit"])}</td><td>{params_html(m["defaults"])}</td></tr>'
        for m in results
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>七种切分策略演示</title>
<style>
  :root{{
    --bg:#f8fafc;--card:#fff;--border:#e2e8f0;--text:#0f172a;--text2:#334155;
    --muted:#64748b;--blue:#2563eb;--green:#059669;--orange:#ea580c;--violet:#6d28d9;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.55;}}
  .page{{max-width:980px;margin:0 auto;padding:28px 22px 60px;}}
  .head{{background:#fff;border:1px solid var(--border);border-radius:14px;padding:20px 24px;margin-bottom:18px;}}
  .head h1{{margin:0 0 6px;font-size:22px;}}
  .head p{{margin:4px 0 0;color:var(--text2);font-size:14px;}}
  table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--border);
    border-radius:12px;overflow:hidden;margin-bottom:18px;}}
  th,td{{border-bottom:1px solid var(--border);padding:10px 12px;font-size:13px;vertical-align:top;text-align:left;}}
  th{{background:#f1f5f9;font-size:13px;}}
  code{{background:#eef2ff;color:#3730a3;border-radius:4px;padding:1px 5px;font-size:12px;}}
  .strat{{background:#fff;border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:16px;}}
  .s-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:12px;}}
  .s-title{{font-size:17px;font-weight:600;}}
  .badge{{display:inline-block;background:var(--violet);color:#fff;border-radius:6px;padding:2px 8px;font-size:12px;margin-right:6px;}}
  .s-count{{color:var(--blue);font-weight:600;font-size:14px;}}
  .s-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;}}
  .s-cell{{background:#f8fafc;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12.5px;color:var(--text2);}}
  .chunks{{display:flex;flex-direction:column;gap:8px;}}
  .ck{{border:1px solid var(--border);border-radius:8px;padding:8px 10px;background:#fff;}}
  .ck-h{{font-size:12px;font-weight:600;color:var(--text);margin-bottom:3px;}}
  .ck-body{{font-size:12.5px;color:var(--text2);white-space:pre-wrap;}}
  .ck-meta{{font-size:11px;color:var(--muted);margin-top:3px;word-break:break-all;}}
  .ck-m{{color:var(--muted);font-weight:400;font-size:11px;}}
  .note{{margin-top:10px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#7c2d12;}}
  .cost-free{{color:var(--green);font-weight:600;}}
  .cost-paid{{color:var(--orange);font-weight:600;}}
  .footer{{margin-top:16px;text-align:center;color:var(--muted);font-size:12px;}}
</style>
</head>
<body>
<div class="page">
  <header class="head">
    <h1>七种切分策略演示</h1>
    <p>同一份混合样例文本（含标题 / 段落 / FAQ / 日志），经 7 种策略真实切片的结果对比。</p>
    <p style="font-size:12.5px;color:var(--muted)">策略代码：<code>backend/app/services/chunking/</code>　·　与上传弹窗 Radio、DB <code>chunk_strategy</code> 字段、环境变量默认规则三方一致</p>
  </header>

  <table>
    <tr><th>策略</th><th>注册名</th><th>适用文档</th><th>默认参数</th></tr>
    {overview}
  </table>

  {sections}

  <p class="footer">RAG 知识库系统 · 多策略智能文本切片模块 · 浅底版</p>
</div>
</body>
</html>"""


def main():
    base = os.path.dirname(os.path.abspath(__file__))  # .../backend/scripts
    out_dir = os.path.abspath(os.path.join(base, "..", "..", "..", "docs"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "切分策略演示-七种策略.html")
    results = []
    for cn, en, inst, desc, suit, cost in STRATEGIES:
        log.info(f"运行策略 {en} ...")
        results.append(run_one(cn, en, inst, desc, suit, cost))
    html_doc = build_html(results)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    log.info(f"已生成：{out_path}")
    for m in results:
        log.info(f"  {m['en']:<13} 切片 {m['count']} 块")


if __name__ == "__main__":
    main()
