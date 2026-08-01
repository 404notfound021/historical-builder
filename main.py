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
from pipeline.eras import get_era
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
    parser.add_argument("--obsidian-root", help="覆盖 Obsidian vault 路径")
    args = parser.parse_args()

    global_config = load_global_config()
    book_config = load_book_config(args.book)

    book_name = book_config["book_name"]
    era = get_era(book_config, global_config)
    obsidian_root = Path(args.obsidian_root or book_config.get("obsidian_root") or global_config["obsidian_root"]).expanduser()
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
        extractor = Extractor(llm, book_config, PROJECT_ROOT / "resource" / "prompts", intermediate_dir, era)
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
        event_extractor = EventExtractor(llm, book_config, PROJECT_ROOT / "resource" / "prompts", intermediate_dir, era)
        events = event_extractor.run(chapters, state)
        (intermediate_dir / "raw_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.mark_phase_done("extract_events")
        return events

    # ===== Phase 3: Dedup =====
    def phase_dedup():
        raw = json.loads((intermediate_dir / "raw_persons.json").read_text(encoding="utf-8"))
        deduper = Deduper(book_config, era)
        merged = deduper.deduplicate(raw)

        # Literary relation fixup: 同僚→主仆/妾室/恋人 (via era)
        if hasattr(era, 'fix_relations'):
            merged = era.fix_relations(merged)

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

    # ===== Phase 3.7: Event Dedup =====
    def phase_event_dedup():
        events_path = intermediate_dir / "linked_events.json"
        if not events_path.exists():
            return
        from pipeline.event_deduper import EventDeduper
        events = json.loads(events_path.read_text(encoding="utf-8"))
        deduper = EventDeduper()
        events = deduper.deduplicate(events)
        events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        state.mark_phase_done("event_dedup")

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
    # ===== Phase 7: Normalize =====
    def phase_normalize():
        resolved = json.loads((intermediate_dir / "resolved_persons.json").read_text(encoding="utf-8"))
        events_path = intermediate_dir / "linked_events.json"
        linked_events = json.loads(events_path.read_text(encoding="utf-8")) if events_path.exists() else []

        # Enrichment (CBDB for ancient, no-op for literary)
        if hasattr(era, 'enrich_person'):
            enriched_count = 0
            for person in resolved:
                if era.enrich_person(person):
                    enriched_count += 1
            if enriched_count:
                print(f"  数据补全: {enriched_count}/{len(resolved)} 人")

        from pipeline.normalizer import Normalizer
        nz = Normalizer(book_config, global_config, era)
        resolved, linked_events = nz.run(resolved, linked_events)

        (intermediate_dir / "resolved_persons.json").write_text(
            json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
        (intermediate_dir / "linked_events.json").write_text(
            json.dumps(linked_events, ensure_ascii=False, indent=2), encoding="utf-8")

        state.mark_phase_done("normalize")
        return resolved

    # ===== Phase 8: Write =====
    def phase_write():
        resolved = json.loads((intermediate_dir / "resolved_persons.json").read_text(encoding="utf-8"))
        chapters_data = json.loads((intermediate_dir / "chapters.json").read_text(encoding="utf-8"))
        chapter_titles = {c["index"]: c["title"] for c in chapters_data}

        metadata = MetadataInjector(book_config, chapter_titles)
        renderer = TemplateRenderer(PROJECT_ROOT / "resource" / "templates", era)
        writer = FileWriter(str(obsidian_root), global_config["output_base"], renderer)

        # Orphan cleanup
        valid_names = {re.sub(r'[<>:"/\\|?*]', '-', p['姓名']) for p in resolved}
        person_dir = writer._build_output_dir(book_config, "人物")
        if person_dir.exists():
            orphan_cleaned = 0
            for f in list(person_dir.glob("*.md")):
                if f.stem not in valid_names:
                    f.unlink(); orphan_cleaned += 1
            if orphan_cleaned:
                print(f"    孤儿文件清理: {orphan_cleaned} 个")

        from pipeline.incremental_writer import IncrementalWriter
        from pipeline.provenance_tracker import ProvenanceTracker
        inc_writer = IncrementalWriter(writer)
        provenance = ProvenanceTracker(PROJECT_ROOT / "output" / book_name / "provenance.json", book_name)

        person_stats = {"新建": 0, "合并": 0, "跳过": 0}
        for person in resolved:
            source_chapters = [idx for idx, _ in person.pop("_source_chapters", [])]
            person = metadata.inject(person, source_chapters)
            chapter_str = chapter_titles.get(source_chapters[0], "") if source_chapters else ""
            provenance.track_person(person, chapter_str)
            if "标签" not in person or not person["标签"]:
                person["标签"] = [era.label]
            path, written, status = inc_writer.write_person_incremental(book_config, person)
            if "新建" in status: person_stats["新建"] += 1
            elif "合并" in status and written: person_stats["合并"] += 1
            else: person_stats["跳过"] += 1

        provenance.save()
        print(f"  人物: 新建 {person_stats['新建']}, 合并 {person_stats['合并']}, 跳过 {person_stats['跳过']}")
        state.mark_phase_done("write")

    # ===== Phase 9: Stubs =====
    def phase_stubs():
        resolved = json.loads((intermediate_dir / "resolved_persons.json").read_text(encoding="utf-8"))
        renderer = TemplateRenderer(PROJECT_ROOT / "resource" / "templates", era)
        writer = FileWriter(str(obsidian_root), global_config["output_base"], renderer)

        from pipeline.stub_generator import StubGenerator
        stub_gen = StubGenerator(writer, renderer, book_config, global_config, intermediate_dir, era)

        linked_events = None
        linked_path = intermediate_dir / "linked_events.json"
        if linked_path.exists():
            try: linked_events = json.loads(linked_path.read_text(encoding="utf-8"))
            except Exception: pass

        stats = stub_gen.generate_all(resolved, linked_events)
        for category, count in stats.items():
            print(f"  {category}: {count} 个")
        state.mark_phase_done("stubs")

    # ===== Phase 10: Finalize =====
    def phase_finalize():
        resolved = json.loads((intermediate_dir / "resolved_persons.json").read_text(encoding="utf-8"))
        renderer = TemplateRenderer(PROJECT_ROOT / "resource" / "templates", era)
        writer = FileWriter(str(obsidian_root), global_config["output_base"], renderer)

        # Source node
        source_folder = global_config.get("source_folder", era.source_folder_default)
        source_rendered = f"""---
类型: {era.source_type}
id: {str(abs(hash(book_name)) % 10**16)}
书名: {book_name}
作者:
成书年代:
体裁:
创建时间: {datetime.now(timezone.utc).isoformat()}
---

# {book_name}

## 概述


## 已抽取人物

"""
        for person in resolved:
            source_rendered += f"- [[{person['姓名']}]]\n"

        source_dir = writer._build_output_dir(book_config, source_folder)
        source_dir.mkdir(parents=True, exist_ok=True)
        source_file = source_dir / f"{book_name}.md"
        if not source_file.exists():
            source_file.write_text(source_rendered, encoding="utf-8")
            print(f"  + {era.source_type}: {book_name}.md")

        # MOC
        from pipeline.moc_generator import MocGenerator
        moc_gen = MocGenerator(writer, book_config, global_config["output_base"])
        moc_count = moc_gen.generate(resolved)
        print(f"  MOC: {moc_count} 个")

        # Clean iCloud conflict files
        import glob
        for subdir in ["人物","事件","地名","职官","MOC"]:
            d = writer._build_output_dir(book_config, subdir)
            for f in glob.glob(str(d / "* 2.md")):
                try: os.remove(f)
                except Exception: pass

        state.mark_phase_done("finalize")

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
    phase_order = ["split", "extract", "extract_events", "dedup", "link", "event_dedup",
                   "wikilink", "normalize", "write", "stubs", "finalize"]

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
        elif phase == "event_dedup":
            phase_event_dedup()
        elif phase == "wikilink":
            phase_wikilink()
        elif phase == "normalize":
            phase_normalize()
        elif phase == "write":
            phase_write()
        elif phase == "stubs":
            phase_stubs()
        elif phase == "finalize":
            phase_finalize()

        state.mark_phase_done(phase)

    print(f"\n{book_config['book_name']} 处理完成")


if __name__ == "__main__":
    main()
