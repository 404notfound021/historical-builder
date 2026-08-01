"""增量写入 —— 读 Obsidian 现有文件，diff → merge → 写回"""

import hashlib
import re
import yaml
from pathlib import Path


def _strip(s: str) -> str:
    s = s.strip()
    while s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s


def _normalize_item(item):
    """归一化列表项（dict 或 string），去掉 wikilink 包裹后比较"""
    if isinstance(item, dict):
        return tuple(sorted((k, _strip(str(v))) for k, v in item.items()))
    if isinstance(item, str):
        return _strip(item)
    return item


class IncrementalWriter:
    def __init__(self, writer):
        self.writer = writer

    def write_person_incremental(self, book_config: dict, person_data: dict) -> tuple[Path, bool, str]:
        output_dir = self.writer._build_output_dir(book_config, "人物")
        filename = self.writer._make_filename(person_data.get("姓名", "Unknown"), person_data.get("朝代", []))
        filepath = output_dir / filename

        if not filepath.exists():
            rendered = self.writer.renderer.render_person(person_data)
            return (*self.writer._write_if_changed(output_dir, filename, rendered), "新建")

        existing = filepath.read_text(encoding="utf-8")
        existing_fm = self._parse_frontmatter(existing)
        new_fm = person_data

        if existing_fm.get("id") == new_fm.get("id"):
            merged = self._merge_same_id(existing_fm, new_fm)
            status = "合并(同UUID)"
        else:
            # 同名异UUID：以新数据为准，旧数据忽略
            merged = new_fm
            status = "覆盖(同名异UUID)"

        rendered = self.writer.renderer.render_person(merged)
        new_hash = self._hash(rendered)
        existing_hash = self._hash(existing)

        if new_hash == existing_hash:
            return filepath, False, f"{status} (未变)"

        filepath.write_text(rendered, encoding="utf-8")
        return filepath, True, status

    def _parse_frontmatter(self, text: str) -> dict:
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return {}
        try:
            data = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return {}
        return self._normalize_frontmatter(data)

    def _normalize_frontmatter(self, data: dict) -> dict:
        """递归剥掉所有字符串值上的 [[ ]] 包裹"""
        if isinstance(data, dict):
            return {k: self._normalize_frontmatter(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._normalize_frontmatter(item) for item in data]
        if isinstance(data, str):
            return _strip(data)
        return data

    def _merge_same_id(self, existing: dict, new_data: dict) -> dict:
        """以新数据为基准，已有数据中仅补充新数据里不存在的内容"""
        merged = dict(new_data)

        # 标量字段：已有非空值补到新数据里（如果新数据无此字段或为空）
        scalar_fields = ["字", "号", "出生地", "出生地今名", "卒地", "卒地今名",
                         "出生地坐标", "卒地坐标", "cbdb_id"]
        for key in scalar_fields:
            exist_val = existing.get(key)
            new_val = merged.get(key)
            if exist_val and exist_val != "无考" and (not new_val or new_val == "无考"):
                merged[key] = exist_val

        # 生卒年：已有值优先（CBDB 补全的数据）
        for key in ["生年", "卒年"]:
            if existing.get(key) and not merged.get(key):
                merged[key] = existing[key]

        # 列表字段：新数据 + 已有中归一化后不在新数据中的条目
        # 参与事件需额外做名称归一化（合并 诛董卓/诛杀董卓 等变体）
        list_fields = ["关系", "历任势力", "官职", "爵位", "参与事件"]
        for list_key in list_fields:
            new_list = merged.get(list_key) or []
            norm_new = {_normalize_item(item) for item in new_list}

            exist_list = existing.get(list_key) or []
            for item in exist_list:
                norm_item = _normalize_item(item)
                # 事件名额外做相似度合并
                if list_key == "参与事件" and isinstance(item, str):
                    merged_already = False
                    for ni in norm_new:
                        if isinstance(ni, str) and len(set(norm_item) & set(ni)) >= min(len(norm_item), len(ni)) * 0.6:
                            merged_already = True
                            break
                    if merged_already:
                        continue
                if norm_item not in norm_new:
                    new_list.append(item)
                    norm_new.add(_normalize_item(item))
            merged[list_key] = new_list

        return merged

    def _hash(self, text: str) -> str:
        cleaned = re.sub(r"创建时间:.*", "", text)
        cleaned = re.sub(r"修改时间:.*", "", cleaned)
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
