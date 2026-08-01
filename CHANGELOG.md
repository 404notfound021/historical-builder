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
