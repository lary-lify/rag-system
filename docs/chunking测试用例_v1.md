# RAG 知识库 · 文档切分策略 测试用例设计 v1

> 对应可执行测试：`backend/tests/unit/test_chunking_strategies.py`（pytest，**97 passed / 0 failed / 0 xfailed**）
> 更新（2026-08-25）：初版发现的 R-01~R-06 共 6 个代码缺陷已全部修复，原 `xfail` 用例已转为正常断言全绿。
> 运行方式：`cd backend && PYTHONPATH=. python -m pytest tests/unit/test_chunking_strategies.py -v`
> 生成日期：2026-08-25

## 0. 测试对象

后端 `backend/app/services/chunking/` 下的 7 种文档切分策略，以及 `kb_service._get_strategy()` 的注册路由：

| 策略 key | 类名 | 说明 |
|---|---|---|
| `fixed_token` | `FixedTokenChunker` | 按 token 数固定窗口切分，带 overlap |
| `semantic` | `SemanticChunker` | 按句间字面余弦相似度切分 |
| `paragraph` | `ParagraphChunker` | 按双换行段落切分，可合并小段 |
| `heading_level` | `HeadingLevelChunker` | 按 markdown/HTML/中文/数字标题切分 |
| `qa_pair` | `QAPairChunker` | 识别问答对（问/答前缀）切分 |
| `recursive` | `RecursiveChunker` | 按分隔符递归切分 |
| `ai_assisted` | `AIAssistedChunker` | 调 DeepSeek 做语义边界检测（兜底 paragraph） |

测试只覆盖**纯算法层**（不依赖 Milvus / DeepSeek / Tongyi / MySQL 真实服务）。AI 策略通过 monkeypatch `sync_http_client_context` 注入假 LLM 响应。

## 1. 测试约定

- 统一契约 helper `_assert_basic_contract(chunks)`：列表、非空、每项为 `ChunkResult`、字段类型正确、`index` 单调且为 `0..n-1`。
- `ai_assisted` 对空/短文本返回 `[]`（`min_chunk_size=50` 兜底），因此不纳入「至少 1 chunk」鲁棒性测试。
- AI 策略单测通过 fake ctx 返回 `[1500, 3000]` 形式的边界数组，验证 `ai_used` 标记与 token 入账单。
- token 估算统一为 `len(content) // 2`（中文按 2 字符≈1 token）。

## 2. 跨策略通用用例（TC-CMN）

| 用例 | 验证点 | 结果 |
|---|---|---|
| `test_all_seven_strategies_registered` | 注册表含全部 7 个 key | PASS |
| `test_name_attribute_matches_registry` | 每个 `.name` 与注册 key 一致 | PASS |
| `test_default_params_for_every_strategy` | `get_default_params()` 返回非空 dict | PASS |
| `test_unknown_strategy_falls_back` | 未知策略回退 `FixedTokenChunker` | PASS |
| `test_empty_string` (parametrize×6) | 空串不抛，至少 1 chunk | PASS |
| `test_short_string` (parametrize×6) | 短串不抛，至少 1 chunk | PASS |
| `test_long_string` (parametrize×6) | 5 万字不卡死 | PASS |

## 3. 各策略用例

### 3.1 fixed_token（TC-FT）
默认 `chunk_size=512 / overlap=128`；验证负/零 chunk_size 兜底、overlap 上限回退 `chunk_size//4`、百万字符有限切分、token 估算、`start_char/end_char` 元数据。**R-01 已修复（None 输入返回空列表）。**

### 3.2 semantic（TC-SEM）
验证单句/空文本单 chunk、话题切换切分、元数据 `sentence_count`、阈值影响、中英文混合。**R-04（默认断句正则缺失）/ R-05（max_chunk_size 失效）已修复。**

### 3.3 paragraph（TC-PARA）
验证双换行切分、`merge_small` 开关、`max_paragraph_size` 触发 flush、空行回退、元数据 `paragraph_count`。

### 3.4 heading_level（TC-HL）
验证 markdown/HTML/中文/数字标题、无标题降级 paragraph、标题元数据字段。**R-02 已修复（markdown `##`/`###` 正确识别层级 2/3，HTML `<h1>`/`<h2>` → 1/2）。**

### 3.5 qa_pair（TC-QA）
验证中文问答对、超长答案截断、过短对过滤、前缀开关、状态机。**R-03 已修复（`Q1./A1.` 编号模式正确捕获问题全文）。**

### 3.6 recursive（TC-REC）
验证长文本切分、短文本单 chunk、`max/min_chunk_size`、overlap、元数据。**R-06 已修复（`_force_split` 到达末尾即 break，百万字符不死循环）。**

### 3.7 ai_assisted（TC-AI）
验证短文本不调 LLM、`enable_ai=False`/无 key 降级、合法 JSON / 文本包裹 JSON 解析、不可解析/HTTP 错误/异常降级、`_clean_boundaries` 去重与越界过滤、`get_last_ai_usage` 读后清空、超时。

## 4. 集成链路（INT）

- 7 策略均可通过 `kb_service._get_strategy(key).split(text, **params)` 直接驱动，与 API `POST /api/documents/upload` 的 `chunk_strategy` 参数一一对应。
- 前端 `DocumentListView.vue` 的 7 个 radio 选项与注册 key 一致，需回归确认每个 key 都能返回非空 chunks。

## 5. 已发现缺陷（Defects）

> **状态更新（2026-08-25）：R-01~R-06 共 6 个代码缺陷已全部修复，对应 `xfail` 用例已转为正常断言并全绿（97 passed）。** 下表记录根因与修复方式。

| ID | 严重度 | 位置 | 现象 | 修复方式 | 状态 |
|---|---|---|---|---|---|
| **R-01** | 中 | `fixed_token.py` `split()` | `text=None` 时 `len(text)` 抛 `TypeError`（注释声称兜底但无空值保护） | 单独拦截 `text is None` 返回 `[]`；空串/非正 chunk_size 保留返回原文单 chunk 的兜底 | ✅ 已修复 |
| **R-02** | 高 | `heading_level.py` `_detect_headings` | `pattern.startswith(r'^#')` 永远 `False`（pattern 实际前缀是 `^(`），导致所有 markdown `##`/`###` 标题 level 错判为 1 | 改为 `pattern.startswith(r'^(#')` 匹配真实前缀；HTML 分支 `^(<h` 不变 | ✅ 已修复 |
| **R-03** | 高 | `qa_pair.py` `_match_question/_match_answer` | `Q1./A1.` 编号模式取 `m.group(1)`（即 `\d+`）而非问题全文 `m.group(2)`，`Q1./A1.` 模式完全识别失败 | 统一取 `m.group(m.lastindex or 1)`（最后一个捕获组=问题/答案全文） | ✅ 已修复 |
| **R-04** | 中 | `semantic.py` `split()` | `params.get("sentence_split_pattern", "")` 默认空串而非 `get_default_params()` 的断句正则；仅传 `similarity_threshold` 时整段被当 1 句 → 单 chunk，语义切分失效 | 默认值改为 `self.get_default_params()["sentence_split_pattern"]` | ✅ 已修复 |
| **R-05** | 中 | `semantic.py` `split()` | 一旦 `current_len ≥ min_size`，`elif`（max_size 强制切）不再被评估，只剩相似度断点；相邻句相似度持续 ≥ threshold 时全部累积成单 chunk，`max_chunk_size` 形同虚设 | 把 max_size 强制切提到独立 `if`（每次循环都检查），相似度 break 作为次级 `elif` | ✅ 已修复 |
| **R-06** | 高 | `recursive.py` `_force_split` | 到达文本末尾后 `start` 被重置回文本内部 → 百万字符死循环卡死 | 到达末尾（`end >= len(text)`）立即 `break`；且 `next_start` 绝不大于 `start` | ✅ 已修复 |

## 6. 覆盖率目标

- 7 策略 × 默认/边界/异常参数：已覆盖。
- 跨策略通用契约 + 注册一致性：已覆盖。
- AI 策略 fake LLM 全分支（合法/包裹/不可解析/异常/无 key）：已覆盖。
- 鲁棒性（空串/短串/5万字）：已覆盖。

## 7. 自动化落地

- 该文件为 `backend/tests/unit/` 下标准 pytest 用例，CI 直接 `pytest tests/unit/` 即可。
- R-01~R-06 已全部修复并删除 `xfail` 标记，当前全绿（97 passed / 0 xfailed）。后续若改动切分算法，运行 `cd backend && PYTHONPATH=. python -m pytest tests/unit/test_chunking_strategies.py -v` 回归即可。
