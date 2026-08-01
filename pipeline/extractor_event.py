"""逐章 LLM 事件抽取 —— 独立 pipeline"""

import json
from pathlib import Path

from pipeline.json_parser import JsonParser, JsonParseError
from pipeline.state_manager import StateManager
from pipeline.chapter_splitter import Chapter

def _is_event_done(state, index):
    return index in state._data.get("events_done", [])



class ExtractionError(Exception):
    def __init__(self, chapter_index: int, reason: str):
        self.chapter_index = chapter_index
        super().__init__(f"第 {chapter_index} 章事件抽取失败: {reason}")


class EventExtractor:
    def __init__(self, llm_client, book_config: dict, prompt_dir: Path, intermediate_dir: Path, era=None):
        self.llm = llm_client
        self.book_config = book_config
        self.prompt_dir = prompt_dir
        self.intermediate_dir = intermediate_dir
        self.parser = JsonParser(era)
        prompt_override = book_config.get("prompt_override", {})
        event_prompt_file = prompt_override.get("event") or "common_extract_event.md"
        self.event_prompt = (prompt_dir / event_prompt_file).read_text(encoding="utf-8")

    def extract_chapter(self, chapter: Chapter) -> list[dict]:
        output_path = self.intermediate_dir / f"ch_{chapter.index:04d}_events.json"
        MAX_CHUNK = 6000

        if len(chapter.text) > MAX_CHUNK:
            return self._extract_chunked(chapter, MAX_CHUNK, 500, output_path)

        user_message = f"原文出处: {chapter.title}\n\n{chapter.text}"
        events = self._call_llm(user_message, chapter)

        for e in events:
            e["_chapter_index"] = chapter.index
            e["_chapter_title"] = chapter.title

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [evt ch_{chapter.index:04d}] {chapter.title} → {len(events)} 事件")

        return events

    def _extract_chunked(self, chapter: Chapter, chunk_size: int, overlap: int, output_path: Path) -> list[dict]:
        all_events = []
        seen_ids = set()
        start = 0
        chunk_i = 0
        while start < len(chapter.text):
            end = min(start + chunk_size, len(chapter.text))
            suffix = f"（第{chunk_i+1}段）" if chunk_i > 0 else ""
            msg = f"原文出处: {chapter.title}{suffix}\n\n{chapter.text[start:end]}"
            try:
                events = self._call_llm(msg, chapter, chunk_i)
            except (JsonParseError, ExtractionError):
                chunk_i += 1
                start = end - overlap if end < len(chapter.text) else len(chapter.text)
                continue

            for e in events:
                eid = e.get("id", "")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    e["_chapter_index"] = chapter.index
                    e["_chapter_title"] = chapter.title
                    all_events.append(e)
            chunk_i += 1
            start = end - overlap if end < len(chapter.text) else len(chapter.text)
            if end >= len(chapter.text):
                break

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(all_events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [evt ch_{chapter.index:04d}] {chapter.title} → {len(all_events)} 事件 ({chunk_i}段)")

        return all_events

    import time as _time
    def _call_llm(self, user_message: str, chapter: Chapter, chunk_idx: int = 0) -> list[dict]:
        import time
        time.sleep(3)
        try:
            return self.parser.parse_event_with_retry(
                self.llm, self.event_prompt, user_message, max_retries=3
            )
        except JsonParseError as e:
            error_path = self.intermediate_dir / f"ch_{chapter.index:04d}_{chunk_idx}_event_error.txt"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(
                f"Chapter: {chapter.title}\nChunk: {chunk_idx}\nError: {e}\n\nRaw text:\n{user_message[-2000:]}",
                encoding="utf-8"
            )
            raise ExtractionError(chapter.index, str(e))

    def run(self, chapters: list[Chapter], state: StateManager, parallel: int = 1) -> list[dict]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        lock = threading.Lock()

        pending = [ch for ch in chapters if not _is_event_done(state, ch.index)]
        all_events = []
        cached_count = 0

        for ch in chapters:
            if _is_event_done(state, ch.index):
                cached_path = self.intermediate_dir / f"ch_{ch.index:04d}_events.json"
                if cached_path.exists():
                    cached = json.loads(cached_path.read_text(encoding="utf-8"))
                    all_events.extend(cached)
                    cached_count += 1

        if not pending:
            print(f"  事件: {cached_count} 章已缓存, 共 {len(all_events)} 条")
            return all_events

        results = [None] * len(pending)
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(self.extract_chapter, ch): i for i, ch in enumerate(pending)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    events = future.result()
                    results[i] = events
                    with lock:
                        state._data.setdefault("events_done", []).append(pending[i].index); state.save()
                except ExtractionError as e:
                    print(f"  [evt ch_{pending[i].index:04d}] FAILED: {e}")

        for events in results:
            if events:
                all_events.extend(events)

        total = len(chapters) - len(pending) + len([r for r in results if r is not None])
        print(f"  事件: {len(all_events)} 条 ({total}/{len(chapters)} 章)")

        return all_events
