"""事件去重 —— 合并同名变体 (如 宝玉砸玉/宝玉摔玉 → 宝玉摔玉)"""
import json
from collections import defaultdict


def _normalize(s: str) -> str:
    """去空格 + 小写"""
    import re
    return re.sub(r"\s+", "", s).lower()


def _name_similarity(a: str, b: str) -> float:
    """Jaccard 相似度 on character bigrams"""
    def bigrams(s):
        return {s[i:i+2] for i in range(len(s)-1)} if len(s) > 1 else {s}
    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return 0
    return len(ba & bb) / len(ba | bb)


class EventDeduper:
    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold

    def deduplicate(self, events: list[dict]) -> list[dict]:
        """按名称相似度 + 朝代分组，合并变体事件"""
        if not events:
            return events

        # Group by dynasty first
        by_dynasty = defaultdict(list)
        for e in events:
            dynasty = e.get("朝代", "") or ""
            by_dynasty[dynasty].append(e)

        merged = []
        for dynasty, group in by_dynasty.items():
            merged.extend(self._merge_group(group))

        if len(merged) < len(events):
            print(f"  事件去重: {len(events)} → {len(merged)}")
        return merged

    def _merge_group(self, events: list[dict]) -> list[dict]:
        """在同朝代内按名称相似度聚类合并"""
        clusters = []
        used = set()

        for i, e1 in enumerate(events):
            if i in used:
                continue
            n1 = _normalize(e1.get("事件名称", ""))
            cluster = [e1]
            used.add(i)

            for j, e2 in enumerate(events):
                if j in used:
                    continue
                n2 = _normalize(e2.get("事件名称", ""))
                sim = _name_similarity(n1, n2)
                if sim >= self.threshold:
                    cluster.append(e2)
                    used.add(j)

            if len(cluster) > 1:
                merged_event = self._merge_events(cluster)
                clusters.append(merged_event)
            else:
                clusters.append(e1)

        return clusters

    def _merge_events(self, group: list[dict]) -> dict:
        """合并一组变体事件：取最短名为主名，合并参与人物"""
        # Pick shortest non-empty name as canonical
        names = [(e.get("事件名称", ""), i) for i, e in enumerate(group) if e.get("事件名称")]
        if not names:
            return group[0]
        names.sort(key=lambda x: len(x[0]))
        canonical_name = names[0][0]

        base = dict(group[0])
        base["事件名称"] = canonical_name
        base["_merged_from"] = [e.get("事件名称", "") for e in group if e.get("事件名称") != canonical_name]

        # Merge participants
        all_participants = []
        seen = set()
        for e in group:
            for p in e.get("参与人物", []):
                pn = str(p).strip()
                if pn and pn not in seen:
                    seen.add(pn)
                    all_participants.append(pn)
        base["参与人物"] = all_participants

        # Merge locations: pick most specific (longest)
        locations = [e.get("地点", "") for e in group if e.get("地点")]
        if locations:
            locations.sort(key=len, reverse=True)
            base["地点"] = locations[0]

        # Use best description (longest non-empty 起因)
        for field in ["起因", "经过", "结果"]:
            candidates = [e.get(field, "") for e in group if e.get(field)]
            if candidates:
                candidates.sort(key=len, reverse=True)
                base[field] = candidates[0]

        return base
