"""MOC 自动生成 —— 按势力/朝代/类别分组索引"""

from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from utils.file_writer import FileWriter


class MocGenerator:
    def __init__(self, writer: FileWriter, book_config: dict, output_dir: str):
        self.writer = writer
        self.book_config = book_config
        self.output_dir = output_dir

    def generate(self, persons: list[dict]) -> int:
        """生成所有 MOC，返回写入数量"""
        now = datetime.now(timezone.utc).isoformat()
        book_name = self.book_config.get("book_name", "")
        count = 0

        count += self._generate_faction_moc(persons, book_name, now)
        count += self._generate_dynasty_moc(persons, book_name, now)

        return count

    def _generate_faction_moc(self, persons: list[dict], book_name: str, now: str) -> int:
        """按势力分组"""
        factions: dict[str, list[dict]] = defaultdict(list)
        for p in persons:
            for s in p.get("历任势力", []):
                faction = s.get("势力", "未知")
                if isinstance(faction, str) and not faction.startswith("[["):
                    factions[faction].append(p)

        if not factions:
            return 0

        rows = []
        for faction in sorted(factions.keys()):
            seen = set()
            rows.append(f"\n## {faction}\n")
            rows.append("| 人物 | 字 | 生卒年 | 角色 |")
            rows.append("|------|-----|--------|------|")
            for p in factions[faction]:
                name = p.get("姓名", "")
                if name in seen:
                    continue
                seen.add(name)
                zi = p.get("字", "—")
                birth = p.get("生年") or "?"
                death = p.get("卒年") or "?"
                role = next((s.get("角色", "") for s in p.get("历任势力", [])
                             if s.get("势力") == faction), "")
                rows.append(f"| [[{name}]] | {zi} | {birth}-{death} | {role} |")

        content = f"""---
类型: MOC
标题: {book_name}人物总览
标签: ["索引", "人物总览"]
创建时间: {now}
---

# {book_name}人物总览

> 自动生成 | 共 {len(persons)} 人

{chr(10).join(rows)}

## Dataview 查询

按势力筛选：
```dataview
TABLE 字, 生年, 卒年, 出生地
FROM "人物"
WHERE contains(朝代, "蜀汉")
SORT 生年 ASC
```

按标签筛选：
```dataview
TABLE 字, 生年, 卒年
FROM "人物"
FROM #历史人物 AND #蜀汉
SORT 生年 ASC
```

全部人物表：
```dataview
TABLE 字, 生年, 卒年, 出生地, 朝代
FROM "人物"
SORT 朝代, 生年 ASC
```
"""
        output_dir = self.writer._build_output_dir(self.book_config, "MOC")
        filepath = output_dir / f"{book_name}人物总览.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        if not filepath.exists() or self._hash(filepath.read_text(encoding="utf-8")) != self._hash(content):
            filepath.write_text(content, encoding="utf-8")
            print(f"  + MOC: {book_name}人物总览.md")
            return 1
        return 0

    def _generate_dynasty_moc(self, persons: list[dict], book_name: str, now: str) -> int:
        """按朝代分组"""
        dynasties: dict[str, list[dict]] = defaultdict(list)
        for p in persons:
            for d in p.get("朝代", []):
                if d and d != "无考":
                    dynasties[d].append(p)

        if len(dynasties) <= 1:
            return 0

        rows = []
        for dynasty in sorted(dynasties.keys()):
            rows.append(f"\n## {dynasty}\n")
            for p in dynasties[dynasty]:
                name = p.get("姓名", "")
                zi = p.get("字", "—")
                rows.append(f"- [[{name}]]（{zi}）")

        content = f"""---
类型: MOC
标题: {book_name}人物（按朝代）
标签: ["索引", "朝代"]
创建时间: {now}
---

# {book_name}人物（按朝代）

> 自动生成

{chr(10).join(rows)}

"""
        output_dir = self.writer._build_output_dir(self.book_config, "MOC")
        filepath = output_dir / f"{book_name}人物_按朝代.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        if not filepath.exists() or self._hash(filepath.read_text(encoding="utf-8")) != self._hash(content):
            filepath.write_text(content, encoding="utf-8")
            print(f"  + MOC: {book_name}人物_按朝代.md")
            return 1
        return 0

    def _hash(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
