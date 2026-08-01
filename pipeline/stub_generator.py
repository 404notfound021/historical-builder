"""实体 stub 生成 —— 高频独立文件，低频聚合到索引表"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import os

from utils.file_writer import FileWriter
from pipeline.template_renderer import TemplateRenderer


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s



def _normalize_event_names(ep: dict) -> dict:
    """合并同名变体: 诛董卓/诛杀董卓/吕布诛董卓 → 诛董卓"""
    # 找含有相同核心词的事件组
    result = {}
    merged = set()
    names = sorted(ep.keys(), key=len)  # 短名优先
    for i, name_i in enumerate(names):
        if name_i in merged:
            continue
        result[name_i] = list(ep[name_i])
        for name_j in names[i+1:]:
            if name_j in merged:
                continue
            # 如果长名包含短名的所有核心字，且长名 > 短名*1.5，合并
            if len(name_j) > len(name_i) * 3:
                continue
            common = set(name_i) & set(name_j)
            if len(common) >= min(len(name_i), len(name_j)) * 0.6:
                for p in ep[name_j]:
                    if p not in result[name_i]:
                        result[name_i].append(p)
                merged.add(name_j)
    return result


def _dedup_era(entries):
    """按名称去重历史沿革条目"""
    seen = set()
    result = []
    for e in entries:
        if e["名称"] not in seen:
            seen.add(e["名称"]); result.append(e)
    return result

def _is_valid_event(name: str, surname_chars: str = "") -> bool:
    """过滤掉 LLM 产生的伪事件（传记碎片/个人行为描述）"""
    if len(name) > 18:
        return False
    if any(c in name for c in "。，；：！？『』「」（）\"'”“"):
        return False
    bad_prefixes = ["被", "与", "攻", "征", "讨", "谏", "斩", "封", "拜", "遣",
                    "上疏", "上书", "上表", "上言", "上封", "请", "令", "使",
                    "以", "率", "从", "随", "降", "奔", "投", "归", "杀", "戮",
                    "颁布", "发布", "下诏", "诏令", "制诏", "禅让", "禅代", "受禅",
                    "废黜", "废", "立", "册立", "册封", "追尊", "追谥",
                    "薨", "卒", "崩", "殂", "死", "病逝", "遇害", "赐死", "处死",
                    "刺杀", "拜访", "访问", "会见", "迎接", "送别", "赏赐",
                    "诛", "杀", "赦免", "流放", "逮捕", "囚禁",
                    "举", "荐", "拔", "辟", "署", "表", "奏", "为"]
    for prefix in bad_prefixes:
        if name.startswith(prefix) and len(name) <= 15:
            return False
    bad_suffixes = ["之争", "继承权", "之乱", "自立", "薨", "卒", "崩", "殂", "被杀", "遇害", "赐死", "处死", "病逝"]
    for suffix in bad_suffixes:
        if name.endswith(suffix) and len(name) <= 12:
            return False
    # 人名+动作: 使用 era 提供的姓氏字符集
    chars = surname_chars or "曹刘孙诸葛司马关张赵马黄"
    for pat in ["征", "伐", "讨", "击", "破", "袭", "攻", "战", "围", "斩", "降", "举", "荐"]:
        if pat in name and any(c in name for c in chars) and len(name) <= 15:
            return False
    if ("因" in name or "被" in name) and len(name) <= 15:
        return False
    if ("与" in name or "、" in name) and len(name) <= 15:
        if any(c in name for c in chars + "吕周陆朱"):
            return False
    return True


class StubGenerator:
    def __init__(self, writer: FileWriter, renderer: TemplateRenderer, book_config: dict,
                 global_config: dict, intermediate_dir: Path, era=None):
        self.writer = writer
        self.renderer = renderer
        self.book_config = book_config
        self.era = era
        self.place_norm = global_config.get("place_normalization", {})
        self.dynasty_name = book_config.get("dynasty_name", "")
        self.intermediate_dir = intermediate_dir

    def generate_all(self, resolved_persons: list[dict], linked_events: list[dict] = None) -> dict:
        """一次性生成所有 stub，返回统计信息"""
        now = datetime.now(timezone.utc).isoformat()
        stats = {}

        stats["事件"] = self._generate_events(resolved_persons, now, linked_events)
        stats["地名"] = self._generate_places(resolved_persons, now, linked_events)
        stats["职官"] = self._generate_positions(resolved_persons, now)

        return stats

    def _generate_events(self, persons: list[dict], now: str, linked_events: list[dict] = None) -> int:
        """事件 stub: 优先用 linked_events 的完整数据"""
        # 构建 linked_events 索引
        event_data_index = {}
        if linked_events:
            print(f"    事件补全: {len(linked_events)} 条完整事件数据")
            for e in linked_events:
                ename = _strip_wikilink(e.get("事件名称", ""))
                if not ename:
                    continue
                if ename not in event_data_index or (
                    e.get("时间") and not event_data_index[ename].get("时间")
                ):
                    event_data_index[ename] = e

        # 收集所有事件，过滤掉碎片文本
        total_raw = 0
        event_persons: dict[str, list[str]] = {}
        rejected = 0
        for p in persons:
            for ev in p.get("参与事件", []):
                ev_name = ev if isinstance(ev, str) else ev.get("事件名称", str(ev))
                ev_name = _strip_wikilink(ev_name)
                if not ev_name or ev_name == "无考":
                    continue
                surnames = self.era.event_filter_surnames if self.era else ""
                if _is_valid_event(ev_name, surnames):
                    event_persons.setdefault(ev_name, []).append(p["姓名"])
                else:
                    rejected += 1

        # 事件名归一化：诛董卓/诛杀董卓/吕布诛董卓 → 诛董卓
        event_persons = _normalize_event_names(event_persons)

        # Render ALL events from linked_events + person events
        all_event_names = set(event_persons.keys())
        if event_data_index:
            all_event_names.update(event_data_index.keys())
        count = 0
        for ev_name in all_event_names:
            # 优先用 event pipeline 的完整数据
            person_names = event_persons.get(ev_name, [])
            rich = event_data_index.get(ev_name, {})
            data = {
                "id": rich.get("id", str(abs(hash(ev_name)) % 10**16)),
                "事件名称": ev_name,
                "时间": rich.get("时间", ""),
                "朝代": rich.get("朝代", self.dynasty_name),
                "地点": rich.get("地点", ""),
                "参与人物": [f"{_strip_wikilink(str(n))}" for n in (rich.get("参与人物", []) or person_names)],
                "涉及势力": rich.get("涉及势力", []),
                "起因": rich.get("起因", ""),
                "经过": rich.get("经过", ""),
                "结果": rich.get("结果", ""),
                "历史意义": rich.get("历史意义", ""),
                "出处史书": self.book_config.get("book_name", ""),
                "出处卷目": rich.get("出处卷目", ""),
                "创建时间": now, "修改时间": now,
            }
            _, w = self.writer.write_event(self.book_config, data)
            if w:
                count += 1
        if rejected > 0:
            print(f"    事件过滤: {rejected} 个碎片已丢弃")
        return count

    def _generate_places(self, persons: list[dict], now: str, linked_events: list[dict] = None) -> int:
        """
        地名策略:
        - ancient: 省级/地级 → 独立文件; 县级/乡镇 → 挂载到上级聚合页; CBDB补全坐标
        - literary: 从事件地点提取虚构地名, 独立文件, 无省层级
        """
        if self.era and hasattr(self.era, 'extract_places'):
            # Literary: 从事件地点提取虚构地名
            place_data = self.era.extract_places(persons, linked_events)
            if place_data and isinstance(place_data, tuple):
                return self._write_literary_places(place_data, now)

        # CBDB 地名补全
        cbdb_enricher = None
        cbdb_path = Path(os.path.expanduser('~/workspace/dev/experiments/cbdb_sqlite/cbdb_20260725.sqlite3'))
        if cbdb_path and cbdb_path.exists():
            from pipeline.cbdb_enricher import CBDBEnricher
            cbdb_enricher = CBDBEnricher(cbdb_path)
        # 收集所有地名
        place_refs: dict[str, list[dict]] = {}  # canonical_name → [{orig, person, field}]
        for p in persons:
            for field in ["出生地", "卒地"]:
                orig = p.get(field, "")
                present = p.get(f"{field}今名", "")
                if not present or present == "无考":
                    continue
                canonical = self.place_norm.get(present, present)
                place_refs.setdefault(canonical, []).append({
                    "原文地名": orig if orig != "无考" else "",
                    "人物": p["姓名"],
                    "类型": "出生地" if field == "出生地" else "卒地",
                })

        count = 0
        provinces: dict[str, list] = {}  # province → list of entries

        for canonical, refs in place_refs.items():
            hierarchy = _parse_hierarchy(canonical)
            province = hierarchy[0] if hierarchy else canonical

            # CBDB 补充坐标
            cbdb_coords = ''
            cbdb_level = ''
            if cbdb_enricher:
                result = cbdb_enricher.query_place(canonical)
                if result:
                    cbdb_coords = result.get('坐标', '')
                    cbdb_level = result.get('行政级别', '')
            if len(hierarchy) <= 2:
                # 省级或地市级 → 独立文件（省本身不自聚合）
                data = self._make_place_data(canonical, refs, hierarchy, now)
                if cbdb_coords:
                    data['坐标'] = cbdb_coords
                if cbdb_level and not data.get('类别'):
                    data['类别'] = [cbdb_level]
                _, w = self.writer.write_place(self.book_config, data)
                if w:
                    count += 1
                # 省本身不需要聚合到自己名下
                if len(hierarchy) > 1:
                    provinces.setdefault(province, []).append((canonical, refs, hierarchy))
            else:
                # 县级以下 → 聚合到省页
                provinces.setdefault(province, []).append((canonical, refs, hierarchy))

        # 为每个省生成/更新聚合页
        for province, entries in provinces.items():
            count += self._write_province_aggregate(province, entries, now)

        if cbdb_enricher:
            cbdb_enricher.close()
        return count

    def _write_literary_places(self, place_data: tuple, now: str) -> int:
        """文学地名: 使用 era.extract_places() 返回的 (place_events, place_persons) 写入文件"""
        import re as _re
        place_events, place_persons = place_data

        count = 0
        output_dir = self.writer._build_output_dir(self.book_config, '地名')
        output_dir.mkdir(parents=True, exist_ok=True)

        for loc, events in sorted(place_events.items()):
            safe = _re.sub(r'[<>:"/\\|?*]', '-', loc)
            filepath = output_dir / f'{safe}.md'

            if filepath.exists():
                continue

            persons_list = list(place_persons.get(loc, set()))
            evt_links = '\n'.join(f'- [[{e}]]' for e in sorted(set(events)))
            person_links = '\n'.join(f'- [[{p}]]' for p in sorted(persons_list)[:30])

            content = f'''---
类型: 地名
id: {str(abs(hash(loc)) % 10**16)}
名称: {loc}
类别: ["文学虚构地点"]
出处史书: "[[{self.book_config.get('book_name','')}]]"
创建时间: {now}
修改时间: {now}
---

# {loc}

## 相关事件

{evt_links}

## 相关人物

{person_links}
'''
            filepath.write_text(content, encoding='utf-8')
            print(f'  + 地名: {loc}.md')
            count += 1

        return count

    def _make_place_data(self, canonical, refs, hierarchy, now):
        return {
            "id": str(abs(hash(canonical)) % 10**16),
            "名称": canonical,
            "类别": [_admin_category(hierarchy[-1])] if hierarchy else [],
            "坐标": "",
            "上级": f"[[{''.join(hierarchy[:-1])}]]" if len(hierarchy) > 1 else "",
            "历史沿革": _dedup_era(
                [{"名称": r.get("原文地名", ""), "时期": self.dynasty_name}
                 for r in refs if r.get("原文地名")]
            ),
            "相关人物": [r["人物"] for r in refs],
            "相关事件": [],
            "创建时间": now, "修改时间": now,
        }

    def _write_province_aggregate(self, province: str, entries: list, now: str) -> int:
        """生成省级聚合页：省.md，内含各地县表格"""
        rows = []
        for canonical, refs, hierarchy in entries:
            county_name = hierarchy[-1]
            persons = "、".join(list(dict.fromkeys(f"[[{r['人物']}]]" for r in refs)))
            orig_names_set = list(dict.fromkeys(
                r["原文地名"] for r in refs if r["原文地名"]
            ))
            orig_names = "、".join(orig_names_set) or canonical
            rows.append(f"| {county_name} | {orig_names} | {self.dynasty_name} | {persons} |")

        table = "| 地名 | 古称 | 时期 | 关联人物 |\n|------|------|------|----------|\n" + "\n".join(rows)

        # 读已有文件，追加内容
        output_dir = self.writer._build_output_dir(self.book_config, "地名")
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{province}.md"

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            # 检查是否已有同名条目
            new_entries = []
            for row in rows:
                county = row.split("|")[1].strip()
                if county not in existing:
                    new_entries.append(row)
            if new_entries:
                content = existing.rstrip() + "\n\n" + "\n".join(new_entries) + "\n"
            else:
                return 0  # 无变化
        else:
            content = f"""---
类型: 地名聚合
名称: {province}
类别: [省级行政区]
创建时间: {now}
修改时间: {now}
---

# {province}

> 自动生成 | 来源：《{self.book_config.get("book_name", "")}》

{table}

"""
        filepath.write_text(content, encoding="utf-8")
        import time; time.sleep(0.2)
        print(f"  + 聚合: {province}.md")
        return 1

    def _generate_positions(self, persons: list[dict], now: str) -> int:
        """
        职官策略:
        - 出现 ≥3 次 → 独立文件
        - 出现 <3 次 → 聚合到 职官总录.md
        """
        counter: Counter = Counter()
        pos_persons: dict[str, list[str]] = {}

        for p in persons:
            for pos in p.get("官职", []):
                name = pos.get("名称", "") if isinstance(pos, dict) else str(pos)
                name = _strip_wikilink(name)
                if name and name != "无考":
                    counter[name] += 1
                    pos_persons.setdefault(name, []).append(p["姓名"])

        count = 0
        low_freq = []
        high_freq_positions = []

        for name, freq in counter.most_common():
            if freq >= 3:
                high_freq_positions.append(name)
                data = {
                    "id": str(abs(hash(name)) % 10**16),
                    "名称": name,
                    "体系": "职事官",
                    "类别": "",
                    "隶属": "",
                    "历代沿革": [{"时期": self.dynasty_name, "品级": "", "职等": "", "说明": ""}],
                    "体系说明": "",
                    "担任人物": pos_persons[name],
                    "创建时间": now, "修改时间": now,
                }
                _, w = self.writer.write_position(self.book_config, data)
                if w:
                    count += 1
            else:
                low_freq.append((name, freq, pos_persons[name]))

        # 低频聚合
        if low_freq:
            rows = []
            for name, freq, pnames in low_freq:
                persons_str = "、".join(f"[[{n}]]" for n in pnames)
                rows.append(f"| {name} | {freq} | {self.dynasty_name} | {persons_str} |")

            table = "| 职官 | 出现次数 | 时期 | 关联人物 |\n|------|----------|------|----------|\n" + "\n".join(rows)

            output_dir = self.writer._build_output_dir(self.book_config, "职官")
            output_dir.mkdir(parents=True, exist_ok=True)
            filepath = output_dir / "职官总录.md"
            content = f"""---
类型: 职官聚合
名称: 职官总录
创建时间: {now}
修改时间: {now}
---

# 职官总录

> 自动生成 | 来源：《{self.book_config.get("book_name", "")}》
> 以下为出现次数 < 3 次的低频职官

{table}

"""
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            print(f"  + 聚合: 职官总录.md")
            count += 1

        return count


def _parse_hierarchy(name: str) -> list[str]:
    """ '山东省临沂市沂南县' → ['山东省', '临沂市', '沂南县'] """
    import re
    parts = []
    remainder = name
    for pat in [r"^(.+?省)", r"^(.+?市)", r"^(.+?县)", r"^(.+?区)", r"^(.+?镇)", r"^(.+?乡)"]:
        m = re.match(pat, remainder)
        if m:
            parts.append(m.group(0))
            remainder = remainder[m.end():]
    if remainder:
        parts.append(remainder)
    return parts if parts else [name]


def _admin_category(name: str) -> str:
    if name.endswith("省"):
        return "省级行政区"
    if name.endswith("市"):
        return "地级行政区"
    if name.endswith("县"):
        return "县级行政区"
    if name.endswith("区"):
        return "县级行政区"
    if name.endswith("镇") or name.endswith("乡"):
        return "乡镇级行政区"
    return ""
