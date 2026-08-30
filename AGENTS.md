# Historical Builder — Agent Guidelines

## 项目定位

从原始典籍文本（历史/文学）中自动化抽取人物、事件、地名、职官，生成 Obsidian 结构化知识图谱。pipeline 核心由 LLM（Qwen2.5-32B）驱动抽取，本地做去重/反链/归一化/别名解析。

## 核心铁律

### Single-Case → Class-Level（最高优先级）
**用户报告的任何一个数据问题，都代表这一类问题的存在。绝不只修报出来的个例。**（通用流程见全局 `kaizen` skill：归类 → 全量扫描 → 根因追踪 → 系统性修复 → 验证归零）

本项目归类口径：别名缺失 / 地名匹配失败 / prompt 缺陷 / schema 丢弃字段 / stub 误生成 / 繁简不匹配。修复后必须重跑 `--phase normalize` 验证同类问题归零。

### 空节点零容忍
**在任何情况下不允许存在空节点。空节点的存在，要么是数据问题，要么是 bug。**

这包括但不限于：
- 别名未合并导致的悬空人物节点（如 `三姑娘` → 应合并到 `贾探春`）
- 关系/事件引用了不存在的 wikilink 目标（如 `[[宝玉]]` 指向不存在的 `宝玉.md`）
- 集体实体/亲属称谓/纯官职被当做人物的无效节点（如 `众幕友`/`贾之母`/`太医`）
- 生平概述为空的节点
- **所有 orphan 文件（人物、事件、地名）必须被 pipeline 的 orphan cleanup 自动清除**

违规处理流程：
1. 归类问题类型（alias/missing stub/garbage/body text wikilink）
2. 扫描全部数据（不仅修报出来的个例）
3. 追踪根因（是 alias dict 缺失？还是 stub_reject_pattern 遗漏？还是 incremental writer merge 污染？）
4. 从源头修 pipeline + 数据层同时加固
5. 重跑验证 → 确认所有目录悬空 wikilink 归零

### 别名别名别名
LLM 按书中称呼提取人物（叙述口吻的"三姑娘""宝二爷"等），必须在 normalizer 阶段解析为正名并合并。防御层次：
- `literary.py:aliases` — 称呼→正名映射字典（per-era，不污染 base）
- `normalizer.py` — 人物节点别名重命名 + 关系目标别名解析 + 事件参与人别名解析
- `incremental_writer.py` — 关系字段必须以新数据为准，禁止旧别名回流
- 每次发现新的悬空别名 wikilink → 补入 aliases 字典

### Base + Enrichment 架构
- `pipeline/eras/base.py` — 通用基类（适用于古代史，如三国志）
- `pipeline/eras/literary.py` — 文学类扩展（关系类型/别名/仆人名单/妾室映射）
- 扩展方式为增量添加（never subtract），绝不关闭 base 类中的类型或规则
- post-processing over re-extraction：能脚本修的不用 LLM 重抽

## 目录结构

```
historical-builder/
├── main.py                    # 入口 + 11-phase 编排器
├── config.yaml                # 全局配置（LLM、路径、地名归一化）
├── book_config/               # 每本书的配置
│   ├── book_sanguozhi.yaml    # 三国志（通用史书 era）
│   └── book_hongloumeng.yaml  # 红楼梦（文学 era）
├── pipeline/
│   ├── eras/                  # era 子系统（base + 增量子类）
│   │   ├── base.py            # 通用基类：关系类型/别名/reject pattern/stub 模板
│   │   └── literary.py        # 文学类：主仆/妾室/恋人 + 红楼梦别名 + 仆人名单
│   ├── chapter_splitter.py    # Phase 1: 分章
│   ├── extractor.py           # Phase 2: LLM 人物抽取
│   ├── extractor_event.py     # Phase 2b: LLM 事件抽取
│   ├── deduper.py             # Phase 3: 人物去重
│   ├── entity_linker.py       # Phase 3.5: 事件-人物关联
│   ├── event_deduper.py       # Phase 3.7: 事件去重
│   ├── wikilink_resolver.py   # Phase 4: 文本字段加 [[wikilink]]
│   ├── normalizer.py          # Phase 7: 数据归一化（唯一数据合同）
│   ├── incremental_writer.py  # Phase 8: 增量写入 + 合并已有数据
│   ├── stub_generator.py      # Phase 9: 事件/地名/职官 stub
│   ├── moc_generator.py       # Phase 10: MOC 索引
│   ├── state_manager.py       # checkpoint/resume
│   ├── metadata.py            # 元数据注入
│   ├── template_renderer.py   # Jinja2 模板渲染
│   ├── json_parser.py         # LLM 输出解析
│   ├── provenance_tracker.py  # 溯源追踪
│   └── cbdb_enricher.py       # CBDB 数据库补全（生卒年/坐标）
├── resource/
│   ├── prompts/               # LLM 抽取提示词
│   │   ├── common_extract_person.md   # 通用人物抽取（史书）
│   │   ├── common_extract_event.md    # 通用事件抽取（史书）
│   │   ├── extract_person_literary.md # 文学人物抽取（红楼梦）
│   │   └── extract_event_literary.md  # 文学事件抽取（红楼梦）
│   ├── templates/             # Obsidian .md 模板（Jinja2）
│   │   ├── person_template.md
│   │   ├── event_template.md
│   │   ├── place_template.md
│   │   └── position_template.md
│   └── source/                # 原始典籍文本
├── utils/
│   ├── llm_client.py          # LLM API 客户端
│   └── file_writer.py         # SHA256 幂等文件写入
├── tests/                     # 单元测试
└── output/                    # 中间产物（按书名分目录）
    └── <book_name>/
        ├── intermediate/      # JSON 中间文件
        ├── state.json         # checkpoint 状态
        └── provenance.json    # 溯源数据
```

## Pipeline 阶段序列

```
split → extract → extract_events → dedup → link → event_dedup
  → wikilink → normalize → write → stubs → finalize
```

关键阶段说明：

| Phase | 名称 | 输入 | 输出 | 说明 |
|-------|------|------|------|------|
| 1 | split | 原始 txt | chapters.json | 按正则分章 |
| 2 | extract | chapters.json | raw_persons.json | LLM 抽取人物 |
| 2b | extract_events | chapters.json | raw_events.json | LLM 抽取事件 |
| 3 | dedup | raw_persons.json | merged_persons.json | 人物去重+合并 |
| 3.5 | link | merged + raw_events | linked_events.json | 事件-人物关联 |
| 3.7 | event_dedup | linked_events.json | linked_events.json | 事件去重(Jaccard) |
| 4 | wikilink | merged_persons.json | resolved_persons.json | 文本字段加 [[wikilink]] |
| **7** | **normalize** | resolved + linked_events | resolved + linked_events | **数据归一化（数据合同）** |
| 8 | write | resolved_persons.json | Obsidian .md 文件 | 增量写入 + orphan cleanup |
| 9 | stubs | resolved + linked_events | 事件/地名/职官 .md | stub 生成 |
| 11 | finalize | — | MOC 索引 | 聚合索引 |

## Normalizer — 唯一数据合同

`normalizer.py:Normalizer.run()` 是所有数据进入 Obsidian 前的最后一道关卡。它在 Phase 7 执行，修改数据时必须考虑以下职责：

1. **wikilink 剥离** — `_strip_all` 将所有 `[[X]]` 还原为纯文本 `X`
2. **关系归一化** — 类型映射 + 去重 + 反向关系补全
3. **事件-人物同步** — 互相校验参与关系 + stub 生成
4. **别名解析**（三层）：
   - 人物节点：`姓名 in aliases` → 改名 → 并入 `其他名号`
   - 关系目标：`rel.人物 in aliases` → 改为正名
   - 事件参与人：`event.参与人物[i] in aliases` → 改为正名
5. **同名合并** — alias 解析后同名节点通过 `_merge_person` 融合
6. **精确删除** — `exact_reject_names` 中的节点直接移除
7. **无效 stub 拦截** — `validate_stub(regex + exact_reject_names)` 拒绝创建垃圾 stub
8. **朝代覆盖** — literary era 统一覆盖为书内朝代（防 LLM 幻觉）

### 数据流关键时序

```
wikilink resolver  → [[三姑娘]] wikilinks 写入 JSON
        ↓
normalizer         → _strip_all 剥 wikilink → alias 解析 → 三姑娘→贾探春
        ↓
template renderer  → 从 JSON 重新生成 [[贾探春]] wikilinks
        ↓
incremental writer → 写入 .md（关系字段以新数据为准，禁止旧别名回流）
```

## Era 系统

每个 era 子类独立维护自己的配置，所有属性通过覆盖实现：

| 属性 | base.py | literary.py | 用途 |
|------|---------|-------------|------|
| `aliases` | `{}` | ~60 条称呼→正名 | 别名解析 |
| `relation_types` | 15 种 | +8 种（恋人/主仆/妾室…） | 关系类型全集 |
| `exact_reject_names` | 无 | ~50 精确名 | 删除无效人物节点 |
| `stub_reject_pattern` | 通用 regex | +文学特化模式 | 拒绝无效 stub |
| `servants` | 无 | ~80 仆人名单 | `fix_relations` 中 同僚→主仆 |
| `garbage_names` | `[]` | `[]`（改用 exact_reject_names） | 子串匹配删除 |
| `validate_stub` | regex only | regex + exact_reject_names | stub 创建前拦截 |

关键原则：
- 每个 era 的配置完全自包含，修改 literary.py 不影响三国志
- `exact_reject_names` 用精确全名匹配（不用子串，避免 `大夫` 误杀 `王大夫`）
- stub_reject_pattern 在 `__init__` 中通过字符串拼接扩展（不覆盖 base）

## 空节点防御清单

修改 pipeline 后必须验证以下指标全部归零：

- [ ] 人物目录：别名节点（三姑娘/宝二爷等）→ 0
- [ ] 人物目录：垃圾节点（众幕友/贾府/大夫等）→ 0
- [ ] 人物目录：无生平概述节点 → 0
- [ ] 事件目录：含别名 wikilink 的旧文件 → 0
- [ ] 地名目录：含别名 wikilink 的旧文件 → 0
- [ ] 全目录：`[[宝玉]]`/`[[黛玉]]`/`[[凤姐]]` 等所有已知别名 wikilink → 0
- [ ] Orphan 文件：无 `人物/` 孤儿，无 `事件/` 孤儿，无 `地名/` 孤儿

## Prompt 生成规范
修改 `resource/prompts/` 下任何 prompt 时按全局 `prompt-engineering` skill 的规范执行（结构层级化 / IF-THEN / 输出协议上提 / JSON key 与代码对齐 / Few-Shot / CoT），不再在本文件重复。

## 已知陷阱

- **Incremental Writer merge 污染**：`_merge_same_id` 对 `关系` 字段执行旧+新合并时，旧文件中的别名（如 `三姑娘`）会被重新注入到已解析的数据中。**关系字段必须以新数据为准，不合并旧数据。**
- **Wikilink resolver 早于 Normalizer**：wikilink phase 在 normalize 之前运行 → 别名 wikilink 先被写入 JSON → normalize 剥掉后模板重建。时序正确但须确保 alias 解析在 normalize 中完整覆盖三方（person/relation/event participants）。
- **Place/Event stub 跳过已存在文件**：stub_generator 对已存在的文件执行 `continue`，不覆盖。**必须在 write phase 中通过 orphan cleanup 先删除所有旧文件，让 stub 阶段重建。**
- **garbage_names 子串误杀**：`garbage_names` 用 `in` 子串匹配（如 `'大夫' in '王大夫'` → True）。**精确名删除必须用 `exact_reject_names` 的全等匹配。**

## 开发约定

- 修改 normalizer 后，从 `--phase normalize` 重跑（利用 checkpoint 跳过 LLM 抽取）
- 新增 era 属性时，优先在子类 `__init__` 的 `super().__init__()` 之前设置（让 base 使用新值）
- 所有 alias/wikilink/stub 相关 fix 必须重跑完整 `--phase normalize`（覆盖 normalize → write → stubs → finalize）
- 验证脚本：扫描悬空 wikilink、空生平概述、垃圾节点残留
- 修改后：更新 CHANGELOG → commit → push
