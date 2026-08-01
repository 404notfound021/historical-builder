"""去重后统一解析 [[wikilink]]"""

import re


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s


class WikilinkResolver:
    def __init__(self, book_config: dict):
        self.book_config = book_config

    def resolve(self, persons: list[dict]) -> list[dict]:
        name_index: dict[str, str] = {}

        for p in persons:
            name = p.get("姓名", "")
            name_index[_normalize(name)] = name

            courtesy = p.get("字", "")
            if courtesy and courtesy != "无考":
                name_index[_normalize(courtesy)] = name

            hao = p.get("号", "")
            if hao and hao != "无考":
                name_index[_normalize(hao)] = name

        resolved_count = 0
        for p in persons:
            for rel in p.get("关系", []):
                if not isinstance(rel, dict):
                    continue
                target = rel.get("人物", "")
                norm = _normalize(_strip_wikilink(target))
                if norm in name_index and name_index[norm] != _normalize(p.get("姓名", "")):
                    rel["人物"] = f"[[{name_index[norm]}]]"
                    resolved_count += 1

            resolved_events = []
            for ev in p.get("参与事件", []):
                ev_str = ev if isinstance(ev, str) else ev.get("事件名称", str(ev))
                if ev_str and ev_str != "无考":
                    resolved_events.append(ev_str)
            p["参与事件"] = resolved_events

        print(f"wikilink 解析: {resolved_count} 条关系链接")
        return persons
