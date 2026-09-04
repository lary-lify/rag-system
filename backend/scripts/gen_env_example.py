"""从 config.py 生成/补全环境变量模板（.env.example / .env.template）。

为什么需要它：
config.py 里 77 个字段，手写模板只覆盖了 45 个，漏掉的 33 个恰好全是 P0
阶段新加的性能调优参数（APP_WORKERS、MILVUS_SHUTDOWN_TIMEOUT、
RAG_GLOBAL_TOP_K、DB_MAX_CONNECTIONS_BUDGET……）。这些正是部署时最需要
按机器规格调整的那一批，却没有出现在模板里——部署者根本不知道它们存在。

根因是两处真源：config.py 定义默认值，模板手抄一份。手抄的那份必然漂移。
所以让模板从 config.py 生成，漂移就不可能再发生。

三种模式：
    --check   只报告差异，不改文件（适合 CI 里当检查项跑）
    --append  只追加模板里缺失的键，保留已有内容与人工注释（默认，无损）
    --full    整份重新生成，覆盖已有人工注释（谨慎使用）

用法（从仓库根目录或 backend/ 执行均可）：
    python scripts/gen_env_example.py --mode check    # 只查键名是否对齐，CI 里当检查项
    python scripts/gen_env_example.py --mode append   # 只补缺失的键（默认，无损）
    python scripts/gen_env_example.py --mode full     # 整份重生成，会覆盖人工注释
    python scripts/gen_env_example.py --mode verify   # 校验模板的值等于代码默认值

三者分工：check 管「有没有」，verify 管「对不对」。只跑 check 会漏掉
「键在、值错了」这类更隐蔽的问题（实测抓到过 UPLOAD_ALLOWED_EXTENSIONS
少一个 csv 的情况）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/scripts -> 仓库根
CONFIG_PATH = Path(__file__).resolve().parent.parent / "app" / "core" / "config.py"
TARGETS = [".env.example", ".env.template"]

FIELD_RE = re.compile(r"^ {4}([A-Z][A-Z0-9_]*)\s*:\s*([^=]+?)\s*=\s*(.+?)\s*$")
SECTION_RE = re.compile(r"^ {4}#\s*-+\s*(.+?)\s*-+\s*$")
DERIVED_MARKER = "    # ---- Derived properties ----"


def parse_config() -> list[dict]:
    """解析 config.py，按出现顺序返回字段及其注释、所属小节。"""
    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    fields: list[dict] = []
    section = ""
    comment_buf: list[str] = []

    for line in lines:
        # 注意顺序：派生属性小节也长得像 `# ---- X ----`，必须先拦下来，
        # 否则会被当成普通小节，把 @property 误收成配置项。
        if line.strip() == DERIVED_MARKER.strip():
            break  # 之后全是派生属性，不是配置项
        m_sec = SECTION_RE.match(line)
        if m_sec:
            section = m_sec.group(1)
            comment_buf = []
            continue
        if line.strip().startswith("#"):
            # 空注释行表示换段落，只取第一段，避免模板过长
            if line.strip() == "#":
                if comment_buf:
                    comment_buf.append("#@break")
            else:
                comment_buf.append(line.strip())
            continue
        m = FIELD_RE.match(line)
        if m:
            name, _type, default = m.groups()
            # 只保留第一段注释（到 #@break 为止）
            comment: list[str] = []
            for c in comment_buf:
                if c == "#@break":
                    break
                comment.append(re.sub(r"^#\s?", "", c))
            fields.append(
                {"name": name, "section": section, "comment": comment, "default": default}
            )
        comment_buf = [] if not line.strip() else comment_buf
        if not line.strip():
            comment_buf = []

    return fields


def render_value(default: str) -> str | None:
    """把 Python 字面量默认值渲染成 env 文件里的值。

    返回 None 表示「该字段无法用 env 值表达」，调用方须整行注释掉。
    典型是 `bool | None = None`：env 里写 `KEY=` 会得到空串，pydantic 会把
    空串当布尔解析并直接抛校验错误（实测会让应用启动失败），而不是回落 None。
    """
    d = default.strip()
    # 去掉行尾 # type: ignore 之类的注解
    d = re.sub(r"\s*#.*$", "", d).strip()
    if d == "None":
        return None
    if d in ('""', "''"):
        return ""
    if d.lower() in ("true", "false"):
        return d.lower()
    # 去掉字符串引号，但不破坏内部引号
    if len(d) >= 2 and d[0] == d[-1] and d[0] in "\"'":
        return d[1:-1]
    return d


def render_block(fields: list[dict]) -> str:
    out: list[str] = []
    current_section = None
    for f in fields:
        if f["section"] != current_section:
            current_section = f["section"]
            out.append("")
            out.append(f"# ---------- {current_section} ----------")
        for c in f["comment"]:
            out.append(f"# {c}" if c else "#")
        value = render_value(f["default"])
        if value is None:
            # 无法用 env 值表达：整行注释掉，避免照抄模板时启动失败
            out.append(
                f"# {f['name']}=   # 默认值 None，无法用空串表示，"
                f"需要时显式写成 true/false"
            )
        else:
            out.append(f"{f['name']}={value}")
    return "\n".join(out)


def existing_keys(path: Path) -> set[str]:
    """模板里已覆盖的键。

    注释掉的 `KEY=` 也算已覆盖：默认值是 None 的字段（如 SQL_ECHO）只能以
    注释形式出现，这是有意为之的记法，不能判成缺失。
    """
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    active = set(re.findall(r"^([A-Z][A-Z0-9_]*)\s*=", text, re.M))
    commented = set(re.findall(r"^#\s*([A-Z][A-Z0-9_]*)\s*=", text, re.M))
    return active | commented


def verify_values(fields: list[dict]) -> int:
    """校验模板里的值不会改变默认行为。

    键名对齐只是及格线。模板里一个错值会在别人照抄时静默改变行为——比如
    UPLOAD_ALLOWED_EXTENSIONS 少了 csv，表现就是「CSV 传不上去」这种与配置
    完全联想不到一起的故障。

    基线必须是纯净的代码默认值。直接 `Settings()` 是错的：config.py 顶层有
    load_dotenv，本地 .env 会先被读进 os.environ，把基线污染成本地开发值
    （本项目就因此误判过一次）。所以先摘掉相关环境变量，再 _env_file=None。
    """
    import os

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/
    from app.core.config import Settings

    names = {f["name"] for f in fields}
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.upper() in names}
    exit_code = 0
    try:
        base = Settings(_env_file=None)
        for rel in TARGETS:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            vals = {
                k: v
                for k, v in __import__("dotenv").dotenv_values(path).items()
                if v is not None
            }
            try:
                loaded = Settings(_env_file=None, **{k.lower(): v for k, v in vals.items()})
            except Exception as e:
                print(f"\n{rel}: 载入失败 -> {e}")
                exit_code = 1
                continue

            diff = []
            for k in vals:
                attr = k.lower()
                if not hasattr(base, attr):
                    continue
                a, b = getattr(base, attr), getattr(loaded, attr)
                if a != b and not (a == "" and b == ""):
                    diff.append((k, a, b))

            print(f"\n{rel}: 载入 {len(vals)} 项")
            if diff:
                exit_code = 1
                print(f"  有 {len(diff)} 项与代码默认值不一致（照抄会改变行为）：")
                for k, a, b in diff:
                    print(f"    {k}: 代码默认 {a!r} -> 模板 {b!r}")
            else:
                print("  全部等于代码默认值 —— 照抄不会改变任何行为")
    finally:
        os.environ.update(saved)
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode", choices=["check", "append", "full", "verify"], default="append"
    )
    args = ap.parse_args()

    fields = parse_config()
    names = [f["name"] for f in fields]
    print(f"config.py 解析到 {len(names)} 个配置项")

    if args.mode == "verify":
        return verify_values(fields)

    exit_code = 0
    for rel in TARGETS:
        path = REPO_ROOT / rel
        keys = existing_keys(path)
        missing = [f for f in fields if f["name"] not in keys]
        stale = sorted(keys - set(names))
        print(f"\n{rel}: 已有 {len(keys)} 个键 | 缺失 {len(missing)} | 废弃 {stale or '无'}")

        if stale:
            print(f"  建议手工删除废弃键: {', '.join(stale)}")

        if args.mode == "check":
            if missing or stale:
                exit_code = 1
            continue

        if args.mode == "full":
            header = (
                "# 由 scripts/gen_env_example.py 从 backend/app/core/config.py 自动生成。\n"
                "# 不要手改本文件：改 config.py 的默认值，然后重新运行生成脚本。\n"
                "# 默认值即代码默认值，部署时按需覆盖即可。\n"
            )
            path.write_text(header + render_block(fields) + "\n", encoding="utf-8")
            print(f"  已重新生成 -> {rel}")
        else:  # append
            if not missing:
                print("  无缺失，跳过")
                continue
            block = (
                "\n\n# ==========================================================\n"
                "# 以下条目由 scripts/gen_env_example.py 从 config.py 自动补全。\n"
                "# 值与注释均取自代码默认值，按需覆盖。\n"
                "# ==========================================================\n"
                + render_block(missing)
                + "\n"
            )
            with path.open("a", encoding="utf-8") as f:
                f.write(block)
            print(f"  已追加 {len(missing)} 个键 -> {rel}")

    if args.mode == "check" and exit_code:
        print("\n检查未通过：模板与 config.py 不同步")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
