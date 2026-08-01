"""Pipeline 状态管理 —— checkpoint/resume"""

import json
from datetime import datetime, timezone
from pathlib import Path


class StateManager:
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self._data: dict = {}

    def init(self, book_name: str, total_chapters: int):
        existing = self._read_file()
        if existing:
            self._data = existing
        else:
            now = datetime.now(timezone.utc).isoformat()
            self._data = {
                "book_name": book_name,
                "phases_done": [],
                "chapters_done": [],
                "total_chapters": total_chapters,
                "started_at": now,
                "updated_at": now,
            }
            self.save()

    def is_phase_done(self, phase: str) -> bool:
        return phase in self._data.get("phases_done", [])

    def mark_phase_done(self, phase: str):
        phases = self._data.setdefault("phases_done", [])
        if phase not in phases:
            phases.append(phase)
        self._touch()

    def is_chapter_done(self, chapter_index: int) -> bool:
        return chapter_index in self._data.get("chapters_done", [])

    def mark_chapter_done(self, chapter_index: int):
        chapters = self._data.setdefault("chapters_done", [])
        if chapter_index not in chapters:
            chapters.append(chapter_index)
        self._touch()

    def reset_phase(self, phase: str):
        phases = self._data.get("phases_done", [])
        if phase in phases:
            phases.remove(phase)
        self._touch()

    def reset_all(self):
        self._data["phases_done"] = []
        self._data["chapters_done"] = []
        self._touch()

    def chapter_count_done(self) -> int:
        return len(self._data.get("chapters_done", []))

    def _touch(self):
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_file(self) -> dict | None:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return None
