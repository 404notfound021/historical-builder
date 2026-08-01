"""Pipeline 元数据注入 —— 出处史书, 出处卷目, 创建时间, 修改时间"""

from datetime import datetime, timezone


class MetadataInjector:
    def __init__(self, book_config: dict, chapter_titles: dict[int, str]):
        self.出处史书 = book_config.get("book_name", "")
        self.chapter_titles = chapter_titles

    def inject(self, person: dict, source_chapters: list[int]) -> dict:
        chapter_strs = [self.chapter_titles.get(i, f"卷{i}") for i in sorted(source_chapters)]
        now = datetime.now(timezone.utc).isoformat()
        person["出处史书"] = self.出处史书
        person.setdefault("出处卷目", "、".join(chapter_strs) if chapter_strs else "")
        person["创建时间"] = now
        person["修改时间"] = now
        return person
