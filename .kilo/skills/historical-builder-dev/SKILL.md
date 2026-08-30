---
name: historical-builder-dev
description: >
  Historical Builder project development conventions. Use this skill when modifying the extraction pipeline,
  creating new era plugins, tuning LLM prompts for entity extraction, fixing dedup/normalizer issues,
  or generating Obsidian knowledge graph output from classical Chinese texts.
---

# Historical Builder Development Guide

## Project Overview

Automated LLM-driven pipeline: classical Chinese texts → structured knowledge graph (people/events/places/positions) → Obsidian vault with `[[wikilink]]` interlinking.

### Tech Stack
- **Python 3.13**, minimal deps: `openai`, `pyyaml`, `python-dotenv`, `jinja2`, `pytest`
- **LLM**: SiliconFlow API, `Qwen/Qwen2.5-32B-Instruct` (extraction), `DeepSeek-V3` (synthesis)
- **Config**: `config.yaml` (global) + `book_config/book_*.yaml` (per-book)
- **Output**: Obsidian `.md` with YAML frontmatter + `[[wikilink]]` bidirectional links

## Git Workflow
- 直接提交 master（无分支/PR）。commit+push 按全局规则自动执行（404notfound021 仓库：改完更新文档 → 自动 commit+push）。

## Core Principles (铁律)

### 1. Single-Case → Class-Level Fix
Every bug is a class of problems (通用流程见全局 `kaizen` skill)。本项目落地：
1. **Classify** — 别名缺失/地名匹配失败/prompt 缺陷/schema 丢字段/stub 误生成/繁简不匹配
2. **Full scan** — 脚本验证同类问题全部数量，不靠猜测
3. **Root cause** — 定位 pipeline/配置/prompt 缺陷
4. **Systemic fix** — 修机制不逐个 patch 数据
5. **Verify** — rerun `--phase normalize` 确认归零

### 2. Empty Node Zero Tolerance
No: unresolved aliases, dangling wikilinks, garbage nodes (collective entities, family titles, pure official titles), empty biographies, orphan files. Orphan cleanup must happen automatically.

### 3. Alias Resolution Priority (3-layer)
1. **literary.py:aliases dict** — narrative voice → canonical name (e.g. `三姑娘 → 贾探春`)
2. **normalizer.py** — person rename + relation targets + event participants
3. **incremental_writer.py** — new data takes precedence, old aliases must not flow back

### 4. Base + Enrichment Architecture
- `base.py` defines all default behavior
- Era subclasses (`ancient.py`, `literary.py`) extend additively
- **Never subtract** base rules in subclasses
- Post-processing preferred over LLM re-extraction

## Pipeline (11 Phases)

```
split → extract → extract_events → dedup → link → event_dedup → wikilink → normalize → write → stubs → finalize
```

### Key Phase Details

**Phase 1 (split):** `chapter_splitter.py` — regex or fixed-chunk split, configured per-book in `book_config/`

**Phase 2a (extract person):** `extractor.py` — LLM per chapter via `ThreadPoolExecutor(4)`, >6K chars auto-segment. Prompts in `resource/prompts/`

**Phase 3.5 (link):** `entity_linker.py` — bidirectional person↔event stitching via participant lists

**Phase 7 (normalize):** `normalizer.py` — THE data contract. Last checkpoint before Obsidian render. Responsibilities:
- Strip wikilinks from fields
- 3-layer alias resolution
- Relation type normalization
- Same-name merging
- Invalid stub blocking
- Dynasty override

**Phase 8 (write):** `incremental_writer.py` — UUID match → merge → SHA256 diff → incremental write. Handles iCloud conflict cleanup.

**Phase 9 (stubs):** `stub_generator.py` — Generate place/position/stub event .md files from person extraction output.

## Era Plugin System

Each era subclass in `pipeline/eras/`:
```python
class LiteraryEra(BaseEra):
    # Override class attributes
    RELATION_TYPES = BaseEra.RELATION_TYPES + ["恋人", "主仆", "妾室", ...]
    ALIASES = {...}  # ~60 entries
    EXACT_REJECT_NAMES = {...}  # ~50 entries
    SERVANT_NAMES = [...]  # ~80 entries
    
    def stub_reject_pattern(self, name):  # Custom rejection logic
        pass
```

Set era attributes **before** `super().__init__()`. New era files auto-discovered.

## Prompt Generation Rules (from Prompt Engineering Guide)

Apply to all LLM prompts in `resource/prompts/`:
1. ✅ Structure with `#` hierarchy
2. ✅ Hard logic labels (IF-THEN pseudocode)
3. ✅ Formula-level mappings (field → type → required flag)
4. ✅ Output protocol isolation (format spec at bottom)
5. ✅ Exact variable name alignment with schema fields
6. ✅ 1 few-shot example per prompt
7. ✅ Explicit CoT triggers for complex extraction

## Known Traps to Avoid

1. **Incremental writer merge pollution** — old aliases re-injected during merge. Fix: normalize BEFORE write.
2. **Wikilink resolver timing** — runs before normalizer, aliases get wikilinked then stripped. This is by design.
3. **Stub generator skips existing** — needs orphan cleanup first. Run full pipeline for new stubs.
4. **Garbage names substring false positives** — use `exact_reject_names` (exact match), not `garbage_names` (substring match).

## Development Cycle

After modifying:
- **Normalizer:** Rerun `python main.py --book <config> --phase normalize`
- **Extractor prompts:** Rerun `python main.py --book <config> --phase extract`
- **Templates:** Rerun `python main.py --book <config> --phase write`
- **Full rerun:** `python main.py --book <config> --force`

## Testing

```bash
python -m pytest tests/ -v
```
Tests validate dedup logic, normalizer, templates, event extraction, and dead-link scanning.

## Output Validation Checklist

After pipeline run, verify:
- [ ] No orphan wikilinks (`tests/test_links.py`)
- [ ] No empty biographies
- [ ] No unresolved aliases in relation fields
- [ ] All person-event links bidirectional
- [ ] Place names normalized to modern names
