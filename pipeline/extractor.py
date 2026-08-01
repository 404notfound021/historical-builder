"""逐章 LLM 人物抽取 —— 支持并行加速"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.json_parser import JsonParser, JsonParseError
from pipeline.state_manager import StateManager
from pipeline.chapter_splitter import Chapter


class ExtractionError(Exception):
    def __init__(self, chapter_index: int, reason: str):
        self.chapter_index = chapter_index
        super().__init__(f"第 {chapter_index} 章抽取失败: {reason}")


class Extractor:
    def __init__(self, llm_client, book_config: dict, prompt_dir: Path, intermediate_dir: Path, era=None):
        self.llm = llm_client
        self.book_config = book_config
        self.prompt_dir = prompt_dir
        self.intermediate_dir = intermediate_dir
        self.parser = JsonParser(era)

        prompt_override = book_config.get("prompt_override", {})
        person_prompt_file = prompt_override.get("person") or "common_extract_person.md"
        self.person_prompt = (prompt_dir / person_prompt_file).read_text(encoding="utf-8")

    def extract_chapter(self, chapter: Chapter) -> list[dict]:
        output_path = self.intermediate_dir / f"ch_{chapter.index:04d}_persons.json"

        MAX_CHUNK = 6000  # 超过此字符数自动分段
        if len(chapter.text) > MAX_CHUNK:
            return self._extract_chunked(chapter, MAX_CHUNK, 500, output_path)

        user_message = f"原文出处: {chapter.title}\n\n{chapter.text}"
        persons = self._call_llm(user_message, chapter)

        persons = [p for p in persons if not p.get("_reject")]
        for p in persons:
            p.pop("_reject", None)
            p["_chapter_index"] = chapter.index
            p["_chapter_title"] = chapter.title

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(persons, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [ch_{chapter.index:04d}] {chapter.title} → {len(persons)} 人")

        return persons

    def _extract_chunked(self, chapter: Chapter, chunk_size: int, overlap: int, output_path: Path) -> list[dict]:
        """超长章节自动分段抽取，段内去重后返回"""
        all_persons = []
        seen_ids = set()
        start = 0
        chunk_i = 0
        while start < len(chapter.text):
            end = min(start + chunk_size, len(chapter.text))
            chunk_text = chapter.text[start:end]
            suffix = f"（第{chunk_i+1}段）" if chunk_i > 0 else ""
            msg = f"原文出处: {chapter.title}{suffix}\n\n{chunk_text}"
            try:
                persons = self._call_llm(msg, chapter, chunk_i)
            except (JsonParseError, ExtractionError) as e:
                chunk_i += 1
                start = end - overlap if end < len(chapter.text) else len(chapter.text)
                continue

            persons = [p for p in persons if not p.get("_reject")]
            for p in persons:
                p.pop("_reject", None)
                pid = p.get("id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    p["_chapter_index"] = chapter.index
                    p["_chapter_title"] = chapter.title
                    all_persons.append(p)
            chunk_i += 1
            start = end - overlap if end < len(chapter.text) else len(chapter.text)
            if end >= len(chapter.text):
                break

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(all_persons, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [ch_{chapter.index:04d}] {chapter.title} → {len(all_persons)} 人 ({chunk_i}段)")

        return all_persons

    def _call_llm(self, user_message: str, chapter: Chapter, chunk_idx: int = 0) -> list[dict]:
        try:
            return self.parser.parse_with_retry(
                self.llm, self.person_prompt, user_message, max_retries=3
            )
        except JsonParseError as e:
            error_path = self.intermediate_dir / f"ch_{chapter.index:04d}_{chunk_idx}_error.txt"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(
                f"Chapter: {chapter.title}\nChunk: {chunk_idx}\nError: {e}\n\nRaw text:\n{user_message[-2000:]}",
                encoding="utf-8"
            )
            raise ExtractionError(chapter.index, str(e))

    def run(self, chapters: list[Chapter], state: StateManager,
            parallel: int = 4) -> list[dict]:
        """并行抽取多章。parallel=1 退化为串行"""
        pending = [ch for ch in chapters if not state.is_chapter_done(ch.index)]

        # 加载已缓存章节
        all_persons = []
        for ch in chapters:
            if state.is_chapter_done(ch.index):
                cached_path = self.intermediate_dir / f"ch_{ch.index:04d}_persons.json"
                if cached_path.exists():
                    cached = json.loads(cached_path.read_text(encoding="utf-8"))
                    all_persons.extend(cached)
                    print(f"  [ch_{ch.index:04d}] {ch.title} → {len(cached)} 人 (cached)")

        if not pending:
            return all_persons

        if parallel == 1:
            results = self._run_sequential(pending, state)
        else:
            results = self._run_parallel(pending, state, parallel)

        for persons in results:
            if persons is not None:
                all_persons.extend(persons)

        succeeded = len([r for r in results if r is not None])
        failed_count = len(pending) - succeeded
        print(f"\n总计抽取 {len(all_persons)} 条人物记录（{succeeded}/{len(chapters)} 章成功）")
        return all_persons

    def _run_sequential(self, chapters: list[Chapter], state: StateManager) -> list:
        results = []
        for ch in chapters:
            try:
                persons = self.extract_chapter(ch)
                state.mark_chapter_done(ch.index)
                results.append(persons)
            except ExtractionError as e:
                print(f"  [ch_{ch.index:04d}] FAILED: {e}")
                results.append(None)
        return results

    def _run_parallel(self, chapters: list[Chapter], state: StateManager,
                      workers: int) -> list:
        results = [None] * len(chapters)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self.extract_chapter, ch): i for i, ch in enumerate(chapters)}
            for future in as_completed(futures):
                i = futures[future]
                ch = chapters[i]
                try:
                    persons = future.result()
                    state.mark_chapter_done(ch.index)
                    results[i] = persons
                except ExtractionError as e:
                    print(f"  [ch_{ch.index:04d}] FAILED: {e}")
        return results
