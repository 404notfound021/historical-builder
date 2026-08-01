"""溯源追踪 —— 记录每个字段的来源"""

import json
from datetime import datetime, timezone
from pathlib import Path


class ProvenanceTracker:
    def __init__(self, output_path: Path, book_name: str):
        self.output_path = output_path
        self.book_name = book_name
        self.records: dict[str, dict] = {}  # person_uuid → {fields: {field: source_info}}

    def load(self):
        if self.output_path.exists():
            self.records = json.loads(self.output_path.read_text(encoding="utf-8"))

    def track_person(self, person: dict, chapter_title: str):
        """记录一个人物的字段来源"""
        pid = person.get("id", "")
        if not pid:
            return

        if pid not in self.records:
            self.records[pid] = {"姓名": person.get("姓名", ""), "字段来源": {}}

        tracked_fields = [
            "字", "号", "朝代", "生年", "卒年", "出生地", "出生地今名",
            "卒地", "卒地今名", "历任势力", "官职", "爵位", "关系",
            "参与事件", "生平概述",
        ]

        for field in tracked_fields:
            val = person.get(field)
            if val is not None and val != "" and val != [] and val != "无考":
                source_key = field
                entry = {
                    "来源": self.book_name,
                    "卷目": chapter_title,
                    "记录时间": datetime.now(timezone.utc).isoformat(),
                }
                self.records[pid]["字段来源"].setdefault(source_key, []).append(entry)

    def save(self):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_field_sources(self, person_id: str, field: str) -> list[dict]:
        """查询某个字段的所有来源"""
        return self.records.get(person_id, {}).get("字段来源", {}).get(field, [])
