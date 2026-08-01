#!/usr/bin/env python3
"""Historical Builder — 史料构建流水线
V2: 人物抽取 → 去重 → wikilink → 地名/职官/事件 stub → 渲染写入 → MOC
"""

import argparse
import json
import os
import re
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

from pipeline.state_manager import StateManager
from pipeline.chapter_splitter import ChapterSplitter
from pipeline.extractor import Extractor
from pipeline.deduper import Deduper
from pipeline.wikilink_resolver import WikilinkResolver
from pipeline.metadata import MetadataInjector
from pipeline.template_renderer import TemplateRenderer
from utils.llm_client import LLMClient
from utils.file_writer import FileWriter


def load_global_config() -> dict:
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_book_config(book_config_path: str) -> dict:
    with open(PROJECT_ROOT / book_config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="史料构建流水线 — 人物抽取")
    parser.add_argument("--book", required=True, help="书籍配置路径")
    parser.add_argument("--force", action="store_true", help="忽略 checkpoint，全量重跑")
    parser.add_argument("--phase", help="只跑指定阶段: split/extract/dedup/wikilink/render")
    parser.add_argument("--dry-run", action="store_true", help="不调 LLM，只验证配置和路径")
    args = parser.parse_args()

    global_config = load_global_config()
    book_config = load_book_config(args.book)

    book_name = book_config["book_name"]
    obsidian_root = Path(global_config["obsidian_root"]).expanduser()
    intermediate_dir = PROJECT_ROOT / "output" / book_name / "intermediate"
    state_path = PROJECT_ROOT / "output" / book_name / "state.json"

    place_norm = global_config.get("place_normalization", {})
    state = StateManager(state_path)

    # ===== Phase 1: Split =====
    def phase_split():
        splitter = ChapterSplitter(book_config)
        source_dir = PROJECT_ROOT / Path(book_config["source_path"]).parent
        chapters = splitter.split(source_dir)
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        chapters_data = [
            {"index": ch.index, "title": ch.title, "text": ch.text, "source_file": ch.source_file}
            for ch in chapters
        ]
        (intermediate_dir / "chapters.json").write_text(
            json.dumps(chapters_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.init(book_name, len(chapters))
        state.mark_phase_done("split")
        print(f"分章完成: {len(chapters)} 章")
        return chapters

    # ===== Phase 2: Extract =====
    def phase_extract(chapters):
        llm = LLMClient(global_config)
        extractor = Extractor(llm, book_config, PROJECT_ROOT / "resource" / "prompts", intermediate_dir)
        persons = extractor.run(chapters, state)
        (intermediate_dir / "raw_persons.json").write_text(
            json.dumps(persons, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.mark_phase_done("extract")
        return persons

    
    # ===== Phase 2b: Extract Events =====
    def phase_extract_events(chapters):
        from pipeline.extractor_event import EventExtractor
        llm = LLMClient(global_config)
        event_extractor = EventExtractor(llm, book_config, PROJECT_ROOT / "resource" / "prompts", intermediate_dir)
        events = event_extractor.run(chapters, state)
        (intermediate_dir / "raw_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.mark_phase_done("extract_events")
        return events

    # ===== Phase 3: Dedup =====
    def phase_dedup():
        raw = json.loads((intermediate_dir / "raw_persons.json").read_text(encoding="utf-8"))
        deduper = Deduper(book_config)
        merged = deduper.deduplicate(raw)
        (intermediate_dir / "merged_persons.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.mark_phase_done("dedup")
        return merged

    
    # ===== Phase 3.5: Entity Link =====
    def phase_link(persons):
        events_path = intermediate_dir / "raw_events.json"
        if not events_path.exists():
            print("  事件数据不存在，跳过实体关联")
            return persons
        from pipeline.entity_linker import EntityLinker
        events = json.loads(events_path.read_text(encoding="utf-8"))
        linker = EntityLinker(book_config)
        persons, events = linker.link(persons, events)
        (intermediate_dir / "linked_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return persons

    # ===== Phase 4: Wikilink =====
    def phase_wikilink():
        merged = json.loads((intermediate_dir / "merged_persons.json").read_text(encoding="utf-8"))
        resolver = WikilinkResolver(book_config)
        resolved = resolver.resolve(merged)
        (intermediate_dir / "resolved_persons.json").write_text(
            json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.mark_phase_done("wikilink")
        return resolved

    # ===== Phase 5: Render & Write =====
    def phase_render():
        resolved = json.loads((intermediate_dir / "resolved_persons.json").read_text(encoding="utf-8"))
        chapters_data = json.loads((intermediate_dir / "chapters.json").read_text(encoding="utf-8"))
        chapter_titles = {c["index"]: c["title"] for c in chapters_data}

        metadata = MetadataInjector(book_config, chapter_titles)
        renderer = TemplateRenderer(PROJECT_ROOT / "resource" / "templates")
        writer = FileWriter(str(obsidian_root), global_config["output_base"], renderer)


        from pipeline.incremental_writer import IncrementalWriter
        from pipeline.provenance_tracker import ProvenanceTracker
        from pipeline.moc_generator import MocGenerator

        inc_writer = IncrementalWriter(writer)
        provenance = ProvenanceTracker(
            PROJECT_ROOT / "output" / book_name / "provenance.json", book_name
        )

        # 0.5: CBDB 补全
        cbdb_path = Path(os.path.expanduser("~/workspace/dev/experiments/cbdb_sqlite/cbdb_20260725.sqlite3"))
        enriched_count = 0
        if cbdb_path.exists():
            from pipeline.cbdb_enricher import CBDBEnricher
            enricher = CBDBEnricher(cbdb_path)
            for person in resolved:
                before = {k: person.get(k) for k in ["生年", "卒年", "字", "出生地"]}
                enricher.enrich_person(person)
                after = {k: person.get(k) for k in ["生年", "卒年", "字", "出生地"]}
                if before != after:
                    enriched_count += 1
            enricher.close()
            print(f"  CBDB 补全: {enriched_count}/{len(resolved)} 人")
        else:
            print("  CBDB: 数据库未找到，跳过补全")

        # 5.0: NORMALIZE — 统一数据合同
        from pipeline.normalizer import Normalizer
        nz = Normalizer(book_config, global_config)

        # Load events
        events_path = intermediate_dir / "linked_events.json"
        linked_events = None
        if events_path.exists():
            linked_events = json.loads(events_path.read_text(encoding="utf-8"))

        resolved, linked_events = nz.run(resolved, linked_events or [])
        if linked_events:
            (intermediate_dir / "linked_events.json").write_text(
                json.dumps(linked_events, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # 5a: 增量写入人物 + 溯源
        person_stats = {"新建": 0, "合并": 0, "跳过": 0}
        for person in resolved:
            source_chapters = [idx for idx, _ in person.pop("_source_chapters", [])]
            person = metadata.inject(person, source_chapters)

            chapter_str = chapter_titles.get(source_chapters[0], "") if source_chapters else ""
            provenance.track_person(person, chapter_str)

            # Final wikilink wrap: ensure all person names in relations have [[ ]]
            for rel in person.get("关系", []):
                if isinstance(rel, dict) and "人物" in rel:
                    tgt = rel["人物"].replace("[[", "").replace("]]", "")
                    rel["人物"] = f"[[{tgt}]]"
            path, written, status = inc_writer.write_person_incremental(book_config, person)
            if "新建" in status:
                person_stats["新建"] += 1
            elif "合并" in status and written:
                person_stats["合并"] += 1
            else:
                person_stats["跳过"] += 1

        provenance.save()
        print(f"  人物: 新建 {person_stats['新建']}, 合并 {person_stats['合并']}, 跳过 {person_stats['跳过']}")

        # 5b: stub 生成
        from pipeline.stub_generator import StubGenerator
        stub_gen = StubGenerator(writer, renderer, book_config, global_config, intermediate_dir)
        # 使用事件pipeline的数据（从raw_events.json读取，link阶段已写入linked_events）
        linked_events = None
        linked_path = intermediate_dir / "linked_events.json"
        if linked_path.exists():
            try: linked_events = json.loads(linked_path.read_text(encoding="utf-8"))
            except Exception: pass
        stats = stub_gen.generate_all(resolved, linked_events)
        for category, count in stats.items():
            print(f"  {category}: {count} 个")

        # 5c: 书籍源节点
        source_data = {
            "id": str(abs(hash(book_name)) % 10**16),
            "类型": "史书",
            "书名": book_name,
            "作者": "",
            "成书年代": "",
            "体裁": "",
            "内容概述": "",
            "创建时间": datetime.now(timezone.utc).isoformat(),
        }
        source_rendered = f"""---
类型: 史书
id: {source_data['id']}
书名: {source_data['书名']}
作者: {source_data['作者']}
成书年代: {source_data['成书年代']}
创建时间: {source_data['创建时间']}
---

# {book_name}

## 概述

{source_data['内容概述']}

## 已抽取人物

"""
        for person in resolved:
            source_rendered += f"- [[{person['姓名']}]]\n"

        source_dir = writer.obsidian_root / writer.output_base / global_config.get("source_folder", "史书")
        source_dir.mkdir(parents=True, exist_ok=True)
        source_file = source_dir / f"{book_name}.md"
        if not source_file.exists():
            source_file.write_text(source_rendered, encoding="utf-8")
            print(f"  + 史书: {book_name}.md")

        # 5d: MOC 生成
        moc_gen = MocGenerator(writer, book_config, global_config["output_base"])
        moc_count = moc_gen.generate(resolved)
        print(f"  MOC: {moc_count} 个")


        # 清理 iCloud 冲突文件（.* 2.md）
        import glob
        for subdir in ["人物", "事件", "地名", "职官", "MOC"]:
            pattern = str(writer.obsidian_root / writer.output_base / subdir / "* 2.md")
            for f in glob.glob(pattern):
                try: os.remove(f)
                except Exception: pass
        
        # 修复四括号：iCloud 回滚导致的 [[[[name]]]] → [[name]]
        from pipeline.normalizer import _s as _strip_br
        import glob as _glob
        quad_fixed = 0
        for subdir in ["人物", "事件"]:
            pattern = str(writer.obsidian_root / writer.output_base / subdir / "*.md")
            for fpath in _glob.glob(pattern):
                try:
                    content = open(fpath).read()
                    if "[[" not in content:
                        continue
                    # Replace [[[[name]]]] → [[name]]
                    fixed = content.replace("[[[[", "[[").replace("]]]]", "]]")
                    if fixed != content:
                        open(fpath, "w").write(fixed)
                        quad_fixed += 1
                except: pass
        if quad_fixed:
            print(f"    四括号修复: {quad_fixed} 个文件")
        state.mark_phase_done("render")

    # ===== Dry run =====
    if args.dry_run:
        print(f"{book_config['book_name']}")
        print(f"  LLM: {global_config['llm']['model']} @ {global_config['llm']['api_base']}")
        print(f"  输出: {obsidian_root / global_config['output_base']}")
        splitter = ChapterSplitter(book_config)
        source_dir = PROJECT_ROOT / Path(book_config["source_path"]).parent
        txts = list(source_dir.glob("*.txt"))
        if not txts:
            print(f"  ⚠ 源文本目录为空: {source_dir}")
        else:
            print(f"  源文本: {txts}")
        return

    # ===== Force =====
    if args.force:
        state.reset_all()

    # ===== Run phases =====
    phase_order = ["split", "extract", "extract_events", "dedup", "link", "wikilink", "render"]

    if args.phase:
        if args.phase not in phase_order:
            print(f"无效阶段: {args.phase}，可选: {', '.join(phase_order)}")
            sys.exit(1)
        start_idx = phase_order.index(args.phase)
        run_phases = phase_order[start_idx:]
        for p in phase_order[:start_idx]:
            state.mark_phase_done(p)
    else:
        run_phases = phase_order

    chapters = None

    for phase in run_phases:
        if state.is_phase_done(phase):
            print(f"[{phase}] 已完成，跳过")
            continue

        print(f"\n{'='*50}")
        print(f"Phase: {phase}")
        print(f"{'='*50}")

        if phase == "split":
            chapters = phase_split()
        elif phase == "extract":
            phase_extract(chapters)
        elif phase == "extract_events":
            if chapters is None:
                ch_data = json.loads((intermediate_dir / "chapters.json").read_text(encoding="utf-8"))
                from pipeline.chapter_splitter import Chapter
                chapters = [Chapter(**c) for c in ch_data]
            phase_extract_events(chapters)
        elif phase == "dedup":
            phase_dedup()
        elif phase == "link":
            merged = json.loads((intermediate_dir / "merged_persons.json").read_text(encoding="utf-8"))
            persons = phase_link(merged)
            # 写回清理后数据
            (intermediate_dir / "merged_persons.json").write_text(
                json.dumps(persons, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        elif phase == "wikilink":
            phase_wikilink()
        elif phase == "render":
            phase_render()

        state.mark_phase_done(phase)

    print(f"\n{book_config['book_name']} 处理完成")


if __name__ == "__main__":
    main()
