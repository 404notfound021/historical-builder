"""跨章人物去重与合并 — era-aware"""
import re


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s


class Deduper:
    def __init__(self, book_config: dict, era=None):
        self.book_config = book_config
        self.era = era

    def canonical_key(self, person: dict) -> str:
        """委托给 era 的去重策略"""
        if self.era:
            return self.era.dedup_key(person)
        name = _normalize(person.get("姓名", ""))
        dynasties = person.get("朝代", [])
        dynasty = dynasties[0] if dynasties else "无考"
        return f"{name}|{dynasty}"

    def deduplicate(self, all_persons: list[dict]) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for p in all_persons:
            key = self.canonical_key(p)
            groups.setdefault(key, []).append(p)

        merged = []
        for key, group in groups.items():
            merged.append(self._merge_group(group))

        merged = self._filter_name_fragments(merged)
        merged = self._normalize_aliases(merged)
        merged = self._filter_unnamed(merged)

        print(f"去重: {len(all_persons)} → {len(merged)} 人")
        return merged

    def _filter_name_fragments(self, persons: list[dict]) -> list[dict]:
        names = {p.get("姓名", "") for p in persons}
        result = []
        for p in persons:
            name = p.get("姓名", "")
            if len(name) <= 2:
                longer_exists = any(
                    n != name and name in n and len(n) > len(name)
                    for n in names
                )
                if longer_exists:
                    continue
            result.append(p)
        if len(result) < len(persons):
            print(f"  名字碎片过滤: {len(persons)} → {len(result)}")
        return result

    def _normalize_aliases(self, persons: list[dict]) -> list[dict]:
        """使用 era.aliases 将别名归一化到主名"""
        aliases = self.era.aliases if self.era else {}
        if not aliases:
            return persons

        for p in persons:
            name = p.get('姓名','')
            if name in aliases:
                p['姓名'] = aliases[name]

        groups = {}
        for p in persons:
            key = self.canonical_key(p)
            groups.setdefault(key, []).append(p)
        merged = []
        for group in groups.values():
            merged.append(self._merge_group(group))
        if len(merged) < len(persons):
            print(f"  别名合并: {len(persons)} → {len(merged)}")
        return merged

    def _filter_unnamed(self, persons: list[dict]) -> list[dict]:
        """使用 era.unnamed_patterns 过滤无名称谓"""
        patterns = self.era.unnamed_patterns if self.era else []
        if not patterns:
            return persons
        result = []
        for p in persons:
            name = p.get('姓名','')
            is_unnamed = any(re.search(pat, name) for pat in patterns)
            if not is_unnamed:
                result.append(p)
        if len(result) < len(persons):
            print(f"  无名人物过滤: {len(persons)} → {len(result)}")
        return result

    def _merge_group(self, group: list[dict]) -> dict:
        if len(group) == 1:
            p = dict(group[0])
            ch_idx = p.pop("_chapter_index", 0)
            ch_title = p.pop("_chapter_title", "")
            p["_source_chapters"] = [(ch_idx, ch_title)]
            return p

        first = group[0]
        merged = dict(first)
        merged.pop("_chapter_index", None)
        merged.pop("_chapter_title", None)

        seen_relations = set()
        seen_events = set()
        bio_summaries = []
        source_chapters = []

        for field in ["字","号","出生地","出生地今名","卒地","卒地今名"]:
            if not merged.get(field) or merged[field] == "无考":
                for p in group[1:]:
                    v = p.get(field)
                    if v and v != "无考":
                        merged[field] = v
                        break

        for field in ["生年","卒年"]:
            if not merged.get(field):
                for p in group[1:]:
                    v = p.get(field)
                    if v:
                        merged[field] = v
                        break

        merged.setdefault("历任势力", [])
        merged.setdefault("官职", [])
        merged.setdefault("爵位", [])
        merged.setdefault("关系", [])
        merged.setdefault("参与事件", [])

        for pf in ["历任势力","官职","爵位"]:
            for p in group[1:]:
                for item in p.get(pf, []):
                    if not isinstance(item, dict): continue
                    norm_item = dict(item)
                    for k in norm_item:
                        if isinstance(norm_item[k], str):
                            norm_item[k] = _strip_wikilink(norm_item[k])
                    if norm_item not in [
                        {kk: _strip_wikilink(vv) if isinstance(vv, str) else vv for kk, vv in mi.items()}
                        for mi in merged[pf]
                    ]:
                        merged[pf].append(item)

        for p in group[1:]:
            for rel in p.get("关系", []):
                if not isinstance(rel, dict): continue
                raw_target = _strip_wikilink(rel.get("人物", ""))
                key = (raw_target, rel.get("关系类型", ""))
                if key not in seen_relations and key[0]:
                    seen_relations.add(key)
                    rel["人物"] = raw_target
                    merged["关系"].append(rel)

        for p in group[1:]:
            for ev in p.get("参与事件", []):
                ename = ev if isinstance(ev, str) else ev.get("事件名称", str(ev))
                ename = _strip_wikilink(ename)
                if ename and ename not in seen_events:
                    seen_events.add(ename)
                    merged["参与事件"].append(ename)

        for p in group:
            bio = p.get("生平概述", "")
            ch = p.get("_chapter_title", "")
            if bio:
                bio_summaries.append((ch, bio))
            ch_idx = p.get("_chapter_index", 0)
            if ch and (ch_idx, ch) not in source_chapters:
                source_chapters.append((ch_idx, ch))

        if bio_summaries:
            bio_summaries.sort(key=lambda x: len(x[1]), reverse=True)
            merged["生平概述"] = bio_summaries[0][1]
            if len(bio_summaries) > 1:
                details = "\n".join(f"- **{t}** {b}" for t, b in bio_summaries[1:])
                merged["各卷记载"] = details

        for i, p in enumerate(group):
            dynasties = p.get("朝代", [])
            if dynasties and dynasties != ["无考"]:
                merged["朝代"] = dynasties
                break

        merged["历任势力"] = self._dedup_factions(merged.get("历任势力", []))
        merged["官职"] = self._dedup_positions(merged.get("官职", []))
        merged["爵位"] = self._dedup_positions(merged.get("爵位", []))

        merged["_source_chapters"] = source_chapters
        return merged

    def _dedup_factions(self, factions: list) -> list:
        seen = {}
        for f in factions:
            if not isinstance(f, dict): continue
            name = _strip_wikilink(f.get("势力", ""))
            if not name: continue
            if name not in seen or (f.get("角色") and f["角色"] not in ("无考","官职","") and
                                    (not seen[name].get("角色") or seen[name].get("角色") in ("无考","官职",""))):
                seen[name] = f
        return list(seen.values())

    def _dedup_positions(self, items: list) -> list:
        seen = {}
        for item in items:
            if not isinstance(item, dict): continue
            name = _strip_wikilink(item.get('名称', item.get('爵名', '')))
            if not name or name == '无考': continue
            if name not in seen:
                seen[name] = item
            else:
                existing_period = seen[name].get('时段', '')
                new_period = item.get('时段', '')
                if new_period and new_period not in ('无考','') and (not existing_period or existing_period in ('无考','')):
                    seen[name] = item
        return list(seen.values())
