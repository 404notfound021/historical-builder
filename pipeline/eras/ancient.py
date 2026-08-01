"""AncientEra — 史书/历史人物 era (三国志等)"""
import os
from pathlib import Path
from pipeline.eras.base import BaseEra

class AncientEra(BaseEra):
    label = "历史人物"
    source_type = "文献"

    def __init__(self, book_config, global_config):
        super().__init__(book_config, global_config)

        # ── 关系类型 (base only, no enrichment) ──
        self.relation_types = set(self.relation_types_base)

        # ── 过滤规则 ──
        self.bad_position_terms = {"夫人","皇帝","皇后","太子","太后","王子","公主","世子","无考"}
        self.garbage_names = ['-东汉','-曹魏','-蜀汉','-东吴','魏晋','曹魏-','皇帝','群臣','百官','公卿','位宫']
        self.title_fix = {
            '高贵乡公髦': ('曹髦', [{'类型':'谥号','名称':'高贵乡公'}]),
            '陈留王奂': ('曹奂', [{'类型':'爵号','名称':'陈留王'}]),
            '齐王芳': ('曹芳', [{'类型':'爵号','名称':'齐王'}]),
        }
        self.dynasty_stubs = {'东汉','西汉','曹魏','蜀汉','东吴','西晋','东晋','倭国'}
        self.place_generic = {'吴地':'扬州','蜀地':'益州','魏地':'中原','秦地':'关中'}
        self.event_filter_surnames = "曹刘孙诸葛司马关张赵马黄吕周陆朱"

        # ── 朝代归一化 ──
        self.dynasty_normalize = {
            "三国":"东汉","三国(蜀)":"蜀汉","三国(魏)":"曹魏","三国(吴)":"东吴",
            "东汉末年":"东汉","汉":"东汉","蜀":"蜀汉","魏":"曹魏","吴":"东吴",
            "三国蜀":"蜀汉","三国魏":"曹魏","三国吴":"东吴","三国时期":"东汉",
        }

    def dedup_key(self, person):
        from pipeline.deduper import _normalize as norm
        name = norm(person.get("姓名", ""))
        dynasties = person.get("朝代", [])
        raw = dynasties[0] if dynasties else "无考"
        dynasty = self.dynasty_normalize.get(norm(raw), norm(raw))
        return f"{name}|{dynasty}"

    def enrich_person(self, person):
        """CBDB 数据库补全"""
        cbdb_path = Path(os.path.expanduser(
            "~/workspace/dev/experiments/cbdb_sqlite/cbdb_20260725.sqlite3"
        ))
        if not cbdb_path.exists():
            return False
        from pipeline.cbdb_enricher import CBDBEnricher
        enricher = CBDBEnricher(cbdb_path)
        before = {k: person.get(k) for k in ["生年","卒年","字","出生地"]}
        enricher.enrich_person(person)
        after = {k: person.get(k) for k in ["生年","卒年","字","出生地"]}
        enricher.close()
        return before != after

    def extract_places(self, persons, events):
        """史书地名: 从人物出生地/卒地提取 + 省聚合"""
        # StubGenerator handles this via the ancient path
        return []  # handled by StubGenerator._generate_places (ancient branch)
