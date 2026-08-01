## v2.2.8 (2026-08-01)

### Fixed
- **复合政权名过滤**: 曹魏-东汉/蜀汉群臣/曹魏皇帝 等垃圾节点不再生成
- Normalizer加garbage pattern过滤

## v2.2.7 (2026-08-01)

### Fixed
- **Jinja2 trim_blocks=False**: 根除字段粘合问题的根本原因
- 所有YAML/Body字段不再拼接在同一条行

## v2.2.6 (2026-08-01)

### Fixed
- **朝代stub自动化**: Normalizer自动生成(曹魏/东汉/蜀汉等)
- UT移除朝代白名单——朝代断链必须报错

## v2.2.5 (2026-08-01)

### Fixed
- iCloud -2冲突文件全面清理(867人物+133事件)
- 清理逻辑移到render开始+结尾双重保障

## v2.2.4 (2026-08-01)

### Added
- **全局断链扫描UT**: test_links.py — 扫描所有md文件中[[link]]，验证节点存在
- 朝代stub节点自动生成
- 事件stub在Normalizer中补全缺失引用

### Fixed
- 地点名称清理(武担之南→成都, 去括号垃圾)
- Stub generator渲染全部linked_events(133→280事件)

### Changed
- 67 UT total

## v2.2.3 (2026-08-01)

### Fixed
- CBDB亲属名括号后缀去重(卞氏(曹丕母)→卞氏)
- 新增UT验证

## v2.2.2 (2026-08-01)

### Fixed
- **331 个关系目标空节点**: Normalizer 补全所有关系引用的缺失人物 stub（不仅是事件参与者）
- 曹昂/曹叡/孙坚 等 331 个被引用但不存在的人物全部自动建 stub

### Added
- UT: `test_missing_target_gets_stub` — 验证关系缺失目标自动补全

## v2.2.1 (2026-08-01)

### Fixed
- **四括号彻底消除**: Normalizer→CBDB→Normalizer 执行顺序修正 + render 末尾自动扫描修复
- **模板字段粘合**: YAML frontmatter 中空字段导致后续字段拼接在同一行
- **"高贵乡公髦"→"曹髦"**: 爵号做姓名 + "夫人"非官职的 LLM 幻觉后处理
- **iCloud 文件回滚**: render 末尾自动扫描修复被 iCloud 回滚的四括号文件

### Changed
- Normalizer 改为永远运行（不再依赖 linked_events 存在）
- CBDB 不再向数据中添加 [[wikilink]] 标记
- 模板 `_strip_wikilink` 改为递归剥除
- 模板关键信息段加入 `or '无考'` 默认值


## v2.2.0 (2026-08-01)

### Added
- **Phase 4.5 Normalize 层** (`pipeline/normalizer.py`) — 渲染前唯一数据合同
  - 剥离所有 wikilink 标记，数据永远纯净
  - 自动补全缺失引用 stub（人物/事件）
  - 关系类型归一化 + 反链自动补全
  - 事件-人物双向同步
  - 无考/空值过滤
- **单元测试** (62 tests, 4 modules)
  - Normalizer: wikilink strip / relation dedup / event sync / stub create / position filter
  - Templates: no [[无考]] / no double brackets / body wikilink / position filtering
  - Events: 30+ filter patterns
  - Dedup: cross-chapter merge / name fragments

### Fixed
- [[无考]] 空节点彻底消除（Normalizer + 模板双重过滤）
- 人物关系双括号反复出现（Normalizer 剥离 → 模板统一包裹）
- 孙权 0 事件（event-participant 同步反向补全）
- 洛阳等空地点节点（place_normalization 映射 + stub 自动生成）
- 关系类型归一化（父子→子, 第二任妻→夫妻 等）
- 官职/爵位 同名去重

### Changed
- 模板: 所有 wikilink 包裹前检查 "无考"/空值
- 模板: body 表格统一 [[wikilink]] 包裹
- 事件过滤: 新增 "病逝" 等 pattern, 长度阈值 20→18
- `_strip_wikilink`: 改为递归剥除（支持三层+）


# Changelog

## v2.1.0 (2026-08-01)

### Added
- 事件独立抽取 pipeline (`extractor_event.py` + `pipeline/entity_linker.py`)
- 事件提取 prompt (`resource/prompts/common_extract_event.md`)
- Phase 3 人物-事件缝合逻辑

### Fixed
- 事件碎片大量过滤 (颁布/禅让/薨/卒/人名+动作 等模式)
- 地名古称重复拼接去重
- wikilink 多层括号嵌套
- `cbdb_id` 与 `姓名` YAML 换行粘连
- iCloud 同步 " 2" 冲突文件自动清理
- 增量写入列表字段重复累积
- 官职/关系/事件重复 (Phase 5.0 数据清洗)

### Removed
- 碎片名过滤 (丕/叡/髦 等 LLM 漏姓名单名)

---

## v2.0.0 (2026-07-31)

### Added
- UUID 生成 + 全中文 frontmatter schema
- 历任势力/官职/爵位/卒因 字段分离
- 扁平目录 (人物/事件/地名/职官/MOC/史书)
- 地名层级化 + 省级聚合页
- 职官高频独立/低频聚合策略
- 增量写入 + SHA256 幂等写入
- provenance.json 溯源追踪
- MOC 自动生成 + Dataview 查询模板
- CBDB 6类数据补全 (别名/地址/亲属/官职/入仕/机构)
- 并行 LLM 抽取 (ThreadPoolExecutor)
- 超长章节自动分段 (>6000 chars)

### Changed
- 模型从 deepseek-ai/DeepSeek-V3 → Qwen/Qwen2.5-32B-Instruct
- API 从 DeepSeek 直连 → 硅基流动 (SiliconFlow)
- 模板 Jinja2 化，替换简单字符串替换
- 分章支持 CP936/GBK 编码 + \r\n 换行符

### Fixed
- 三国志 CP936 编码读取
- 源文本 \r\n 换行导致分章失败
- 人物重复抽取 (1215→738)

---

## v1.0.0 (骨架)

### Added
- 基础项目结构
- LLM 客户端 (OpenAI 兼容)
- RAG 引擎骨架
- 嵌入向量骨架
- 文件写入骨架
- 《三国志》配置模板
