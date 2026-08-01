# Historical Builder — 完整架构 v2.0

## 输入与输出

```
输入:  resource/source/{book}/*.txt     → 输出: Obsidian 枢机智库/Raw_Source/History/
       逐章切分                               ├── 人物/  701 个 .md
       按策略抽取                              ├── 事件/  559 个 .md  (to-be: ~150 高质量)
       实体关联                                ├── 地名/   96 个 .md
       去重合并                                ├── 职官/  210 个 .md
       渲染写入                                ├── MOC/     2 个 .md
                                              └── 史书/    1 个 .md
```

## 节点体系

### 人物 (person)
```
id | 姓名 | 字 | 号 | 其他名号 | 朝代[] | 生年 | 卒年
出生地 | 出生地今名 | 出生地坐标 | 卒地 | 卒地今名 | 卒地坐标 | 卒因
历任势力[{势力,时段,角色}]
官职[{名称,时段,性质}]           → [[职官节点]]
爵位[{爵名,册封时间}]
关系[{人物,关系类型}]             → [[其他人物]]
参与事件[]                         → [[事件节点]]
生平概述 | 各卷记载 | 出处史书 | 出处卷目
标签[] | cbdb_id | 入仕途径 | 关联机构
```

### 事件 (event)
```
id | 事件名称 | 时间 | 朝代 | 地点     → [[地名节点]]
参与人物[]                           → [[人物节点]]
涉及势力[] | 起因 | 经过 | 结果 | 历史意义
出处史书 | 出处卷目 | 标签[]
```

### 地名 (place)
```
id | 名称 | 类别[] | 坐标 | 上级      → [[上级地名]]
历史沿革[{名称,时期}]
相关人物[] | 相关事件[]               ← Pipeline 反链填充
标签[]
```

### 职官 (position)
```
id | 名称 | 体系 | 类别 | 隶属
历代沿革[{时期,品级,职等,说明}]
体系说明 | 担任人物[]                 ← Pipeline 反链填充
标签[]
```

## Pipeline 8 阶段

```
Phase 1: SPLIT
  ChapterSplitter: .txt → List[Chapter]
  策略: regex (纪传体) / fixed_chunk (编年体)
  → chapters.json

Phase 2a: EXTRACT_PERSON (已有)
  逐章 LLM → 人物 JSON
  prompt: extract_person.md
  并行: ThreadPoolExecutor(4)
  超长章节自动分段 (>6K chars)
  → ch_{i}_persons.json → raw_persons.json

Phase 2b: EXTRACT_EVENT (新建)
  逐章 LLM → 事件 JSON
  prompt: extract_event.md
  并行: ThreadPoolExecutor(4)
  超长章节自动分段 (>6K chars)
  → ch_{i}_events.json → raw_events.json

Phase 3: ENTITY_LINK (新建)
  事件-人物缝合: person["参与事件"] ↔ event["参与人物"]
  双向补充: 事件中的人物追加到人物参与事件，人物参与事件追加到事件参与人物
  → resolved_persons.json + resolved_events.json

Phase 4: DEDUP
  人物: name+dynasty 分组 → 规则合并 → 碎片名过滤
  事件: event_name+date 分组 → 规则合并
  → merged_persons.json + merged_events.json

Phase 5: WIKILINK
  构建 name_index (含 字/号/别名)
  解析 relations[].人物 → [[name]]
  → resolved_persons.json + resolved_events.json

Phase 6: STUB + ENRICH
  6a: 事件 stub 生成 + 质量过滤
  6b: 地名 stub 生成 (LLM今名 → place_normalization → 省聚合)
  6c: 职官 stub 生成 (去重 + 高频独立/低频聚合)
  6d: CBDB 人物补全 (6类: 别名/地址/亲属/官职/入仕/机构)
  6e: 数据清洗 (官职/关系/事件 去重)

Phase 7: RENDER
  IncrementalWriter: 读Obsidian → UUID匹配 → merge → SHA256 → 增量写回
  provenance.json 溯源追踪
  清理 iCloud 冲突文件

Phase 8: MOC
  按势力/朝代生成索引页 + Dataview 查询模板
  生成史书元数据节点
```

## 关键架构决策

### 人物-事件缝合 (Phase 3)
- 人物管道仍输出 `参与事件` (仅作引用名)
- 事件管道产出完整事件数据 (权威源)
- Phase 3 按事件名匹配，缝合后替换为 [[wikilink]]
- Phase 3 放 Phase 4 (去重) 之后——去重后名称才最终确定

### 地名/职官生成
- 人物管道产出原文地名 → place_normalization → 去重 → 创建唯一地名节点
- 人物管道产出官职名 → 去重 → 创建唯一职官节点
- 高频独立文件，低频聚合到索引表
- 地名历史沿革、职官历代沿革 → 在节点内累积，不拆文件

### 增量写入
- 读 Obsidian 已有文件 → 解析 frontmatter → UUID 匹配
- 已有人物：合并新字段，已有不覆盖
- 新人物：直接创建
- SHA256 对比 (剔除时间戳) → 内容不变则跳过

## Prompt 策略

| Pipeline | Prompt | 专注 | 不关心 |
|----------|--------|------|--------|
| Person extract | extract_person.md | 人物字段/关系/势力 | 事件详情 |
| Event extract | extract_event.md | 事件时间/地点/叙事 | 人物详情 |

## 模型选型

- 结构化抽取: Qwen/Qwen2.5-32B-Instruct (SiliconFlow)
- 叙述合成: deepseek-ai/DeepSeek-V3
- 实体消歧: 本地 BGE-M3 embedding

## 目录结构

```
historical-builder/
├── main.py                         # 8阶段编排器
├── config.yaml                     # 全局配置
├── ARCHITECTURE.md                 # 本文档
├── CHANGELOG.md                    # 变更记录
├── pipeline/
│   ├── state_manager.py            # checkpoint/resume
│   ├── chapter_splitter.py         # 分章 (regex/fixed_chunk)
│   ├── json_parser.py              # JSON校验 + UUID
│   ├── extractor.py                # 人物抽取 (并行+chunking)
│   ├── extractor_event.py          # 事件抽取 (new)
│   ├── deduper.py                  # 去重 + 碎片名过滤
│   ├── entity_linker.py            # 人物-事件缝合 (new)
│   ├── wikilink_resolver.py        # [[link]] 解析
│   ├── stub_generator.py           # 地名/职官/事件 stub
│   ├── cbdb_enricher.py            # CBDB 6类补全
│   ├── incremental_writer.py       # 增量写入
│   ├── provenance_tracker.py       # 溯源
│   ├── moc_generator.py            # MOC索引
│   └── metadata.py                 # 元数据注入
├── utils/
│   ├── llm_client.py               # LLM 客户端 (+retry)
│   └── file_writer.py              # 文件写入 (SHA256幂等)
├── resource/
│   ├── prompts/                    # LLM prompts
│   ├── templates/                  # Jinja2 模板
│   └── source/                     # 原始典籍文本
├── book_config/                    # 每书独立配置
└── output/{book}/                  # 中间产物 (.gitignored)
```
