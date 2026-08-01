"""跨章人物去重与合并"""

import re


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _strip_wikilink(s: str) -> str:
    """剥掉 [[ ]] 包裹，返回纯文本"""
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s


DYNASTY_NORMALIZE = {
    "三国": "东汉", "三国(蜀)": "蜀汉", "三国(魏)": "曹魏", "三国(吴)": "东吴",
    "东汉末年": "东汉", "汉": "东汉", "蜀": "蜀汉", "魏": "曹魏", "吴": "东吴",
    "三国蜀": "蜀汉", "三国魏": "曹魏", "三国吴": "东吴", "三国时期": "东汉",
}


def _norm_dynasty(d: str) -> str:
    d = _normalize(d)
    return DYNASTY_NORMALIZE.get(d, d)


class Deduper:
    def __init__(self, book_config: dict):
        self.book_config = book_config

    def canonical_key(self, person: dict) -> str:
        name = _normalize(person.get("姓名", ""))
        dynasties = person.get("朝代", [])
        dynasty = _norm_dynasty(dynasties[0]) if dynasties else "无考"
        return f"{name}|{dynasty}"

    def deduplicate(self, all_persons: list[dict]) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for p in all_persons:
            key = self.canonical_key(p)
            groups.setdefault(key, []).append(p)

        merged = []
        for key, group in groups.items():
            merged.append(self._merge_group(group))

        # 过滤名字碎片：单字/两字名且是另一人物的子串
        merged = self._filter_name_fragments(merged)

        # 别名归一化 + 无名称谓过滤
        merged = self._normalize_aliases(merged)
        merged = self._filter_unnamed(merged)

        print(f"去重: {len(all_persons)} → {len(merged)} 人")
        return merged

    def _filter_name_fragments(self, persons: list[dict]) -> list[dict]:
        """过滤 LLM 漏了姓氏的单名（如'丕'→已在'曹丕'中存在）"""
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

    # ── 文学别名映射（era=literary 时启用） ──
    LITERARY_ALIASES = {
        '宝玉':'贾宝玉','黛玉':'林黛玉','宝钗':'薛宝钗','凤姐':'王熙凤',
        '凤姐儿':'王熙凤','湘云':'史湘云','宝琴':'薛宝琴','岫烟':'邢岫烟',
        '探春':'贾探春','迎春':'贾迎春','惜春':'贾惜春','元春':'贾元春',
        '巧姐':'贾巧姐','巧姐儿':'贾巧姐','金桂':'夏金桂',
        '贾妃':'贾元春','元妃':'贾元春','代儒':'贾代儒',
        '可卿':'秦可卿','五儿':'柳五儿','刘姥姥':'刘老老',
        '贾蓉媳妇':'秦可卿','贾蓉的媳妇':'秦可卿',
        '秦氏':'秦可卿','贾珠之妻李氏':'李纨','李宫裁':'李纨',
        '大姐儿':'贾巧姐','龄官':'龄官','藕官':'藕官',
        '芳官':'芳官','蕊官':'蕊官','葵官':'葵官','艾官':'艾官',
        '豆官':'豆官','茄官':'茄官','药官':'药官','文官':'文官',
    }

    # ── 无名称谓 pattern（任何 era 启用） ──
    UNNAMED_PATTERNS = [
        r'的(?:娘|妈|母亲|父亲|哥哥|弟弟|姐姐|妹妹|儿子|女儿|孙子|孙女|'
        r'表兄|表弟|表哥|表姐|表妹|干娘|干儿子|嫂子|婆婆|大娘|奶奶|爷|'
        r'姑姑|姑妈|姨妈|舅舅|叔叔|婶婶|女人|男人|师傅|姑娘)$',
        r'媳妇$', r'家的$', r'的女人$', r'的哥哥$', r'的弟弟$', r'的儿子$', r'的母亲$', r'的父亲$',
        r'^两个', r'们$', r'众人$', r'几个', r'其他成员$',
        r'[（(].+[）)]',  # 含括号的别名如 '宝玉（另一个）'
    ]

    def _normalize_aliases(self, persons: list[dict]) -> list[dict]:
        """era=literary 时，将别名归一化到主名"""
        era = self.book_config.get('era', 'ancient')
        if era != 'literary':
            return persons

        for p in persons:
            name = p.get('姓名','')
            if name in self.LITERARY_ALIASES:
                p['姓名'] = self.LITERARY_ALIASES[name]

        # 合并归一化后的同名人物
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
        """过滤以称呼/关系代替姓名的无名人物"""
        import re
        result = []
        for p in persons:
            name = p.get('姓名','')
            is_unnamed = False
            for pat in self.UNNAMED_PATTERNS:
                if re.search(pat, name):
                    is_unnamed = True
                    break
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

        for field in ["字", "号", "出生地", "出生地今名", "卒地", "卒地今名"]:
            if not merged.get(field) or merged[field] == "无考":
                for p in group[1:]:
                    v = p.get(field)
                    if v and v != "无考":
                        merged[field] = v
                        break

        for field in ["生年", "卒年"]:
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

        for pf in ["历任势力", "官职", "爵位"]:
            for p in group[1:]:
                for item in p.get(pf, []):
                    if not isinstance(item, dict):
                        continue
                    # 剥掉 wikilink 后比较去重
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
                if not isinstance(rel, dict):
                    continue
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

        # 去重历任势力（同势力只保留最完整的一条）
        merged["历任势力"] = self._dedup_factions(merged.get("历任势力", []))
        merged["官职"] = self._dedup_positions(merged.get("官职", []))
        merged["爵位"] = self._dedup_positions(merged.get("爵位", []))

        merged["_source_chapters"] = source_chapters
        return merged

    def _dedup_factions(self, factions: list) -> list:
        seen = {}
        for f in factions:
            if not isinstance(f, dict):
                continue
            name = _strip_wikilink(f.get("势力", ""))
            if not name:
                continue
            if name not in seen or (f.get("角色") and f["角色"] not in ("无考", "官职", "") and
                                    (not seen[name].get("角色") or seen[name].get("角色") in ("无考", "官职", ""))):
                seen[name] = f
        return list(seen.values())


    def _dedup_positions(self, items: list) -> list:
        """去重官职/爵位：同名保留最完整的一条"""
        seen = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _strip_wikilink(item.get('名称', item.get('爵名', '')))
            if not name or name == '无考':
                continue
            if name not in seen:
                seen[name] = item
            else:
                # 保留时段更完整的那条
                existing_period = seen[name].get('时段', '')
                new_period = item.get('时段', '')
                if new_period and new_period not in ('无考', '') and (not existing_period or existing_period in ('无考', '')):
                    seen[name] = item
        return list(seen.values())
