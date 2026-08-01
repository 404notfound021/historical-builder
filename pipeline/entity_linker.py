"""实体关联 —— 人物-事件双向缝合"""

import re


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s


class EntityLinker:
    def __init__(self, book_config: dict):
        self.book_config = book_config

    def link(self, persons: list[dict], events: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        双向缝合人物和事件：
        1. 构建人名索引（含 字/号）
        2. 事件中的人物追加到对应人物
        3. 人物中的事件追加到对应事件
        """
        # 构建人名索引
        person_index: dict[str, str] = {}
        for p in persons:
            name = p.get("姓名", "")
            person_index[_normalize(name)] = name
            if p.get("字") and p["字"] != "无考":
                person_index[_normalize(p["字"])] = name
            if p.get("号") and p["号"] != "无考":
                person_index[_normalize(p["号"])] = name

        # 构建事件索引
        event_index: dict[str, dict] = {}
        for e in events:
            ename = e.get("事件名称", "")
            if ename:
                event_index[_normalize(ename)] = e

        # Pass 1: 事件 → 人物。事件中提到的人物追加到人物的参与事件
        for e in events:
            ename = e.get("事件名称", "")
            for pname in e.get("参与人物", []):
                pname = _strip_wikilink(str(pname))
                norm = _normalize(pname)
                person_name = person_index.get(norm, pname)
                for p in persons:
                    if _normalize(p.get("姓名", "")) == _normalize(person_name):
                        if ename not in [str(x) for x in p.get("参与事件", [])]:
                            p.setdefault("参与事件", []).append(ename)
                        break

        # Pass 2: 人物 → 事件。人物中提到的事件追加到事件的参与人物
        for p in persons:
            pname = p.get("姓名", "")
            for ename in p.get("参与事件", []):
                ename = _strip_wikilink(str(ename))
                norm = _normalize(ename)
                if norm in event_index:
                    evt = event_index[norm]
                    if pname not in [str(x) for x in evt.get("参与人物", [])]:
                        evt.setdefault("参与人物", []).append(pname)

        linked_count = sum(
            1 for p in persons
            for e in p.get("参与事件", [])
            if str(e) in event_index
        )
        # Cleanup: replace each person's 参与事件 with only the matched ones
        clean_count = 0
        for p in persons:
            old_events = p.get("参与事件", [])
            p["参与事件"] = [e for e in old_events if _normalize(str(e)) in event_index]
            clean_count += len(old_events) - len(p["参与事件"])
        print(f"实体关联: {linked_count} 条链接, 清理 {clean_count} 个碎片事件")

        return persons, events
