# Historical Builder

从原始典籍文本自动抽取人物/事件，生成 Obsidian 结构化知识图谱。

## 架构

8 阶段 pipeline：Split → Person Extract → Event Extract → Entity Link → Dedup → Wikilink → Stub+Enrich → Render → Obsidian

支持 checkpoint/resume、并行 LLM 抽取、增量写入。详细架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 输出（以《三国志》为例）

| 类别 | 数量 | 内容 |
|------|------|------|
| 人物 | ~740 | UUID + 全中文 frontmatter + [[wikilink]] 双向链接 |
| 事件 | ~120 | 时间/地点/起因/经过/结果/历史意义 完整字段 |
| 地名 | ~80 | 今名标准化 + 省聚合 + 历史沿革 |
| 职官 | ~200 | 体系/类别/历代沿革/担任人物反链 |
| MOC | 2 | 按势力+朝代自动生成索引 |
| 史书 | 1 | 数据来源元信息 |

## 数据源

- **LLM 抽取**：Qwen2.5-32B（硅基流动 API），人物 + 事件独立 prompt
- **CBDB 补全**：哈佛中国历代人物传记数据库，6 类字段自动补全
- **本地处理**：去重/反链/关系归一化/事件碎片过滤

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入硅基流动 API Key
mkdir -p resource/source/三国志 && cp 三国志.txt resource/source/三国志/
python main.py --book book_config/book_sanguozhi.yaml
```

## 添加新书

1. 原始文本放入 `resource/source/<书名>/`
2. 创建 `book_config/book_xxx.yaml`（参考 book_sanguozhi.yaml）
3. `python main.py --book book_config/book_xxx.yaml`

## 模型

| 场景 | 模型 | 提供商 |
|------|------|--------|
| 结构化抽取 | Qwen/Qwen2.5-32B-Instruct | 硅基流动 |
| 叙述合成 | deepseek-ai/DeepSeek-V3 | 硅基流动 |
| 嵌入 | BAAI/bge-m3 | 免费 |
| 补全 | CBDB SQLite | 本地 |

## 项目结构

```
historical-builder/
├── main.py                  # Pipeline 编排器
├── config.yaml              # 全局配置
├── ARCHITECTURE.md          # 完整架构
├── CHANGELOG.md             # 变更记录
├── pipeline/                # Pipeline 模块（8 阶段）
├── utils/                   # LLM 客户端 + 文件写入
├── resource/                # Prompt + 模板 + 源文本
├── book_config/             # 每书独立配置
└── output/                  # 中间产物（不进 Git）
```

## License

MIT
