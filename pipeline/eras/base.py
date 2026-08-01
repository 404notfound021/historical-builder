"""BaseEra — 所有 Era 的抽象接口"""
import re, uuid
from datetime import datetime, timezone

class BaseEra:
    """每个 Era 子类覆盖以下属性和方法"""

    # ── 元数据 ──
    label: str = "人物"                # 标签，如"历史人物"/"文学人物"
    source_type: str = "文献"          # 源节点类型名
    source_folder_default: str = "文献"
    source_heading: str = "史料出处"   # 模板中的出处标题
    dynasty_override: str = None       # 若设置，强制覆盖无考/空朝代

    # ── 模板 ──
    template_person: str = "person_template.md"
    template_event: str = "event_template.md"
    template_place: str = "place_template.md"
    template_position: str = "position_template.md"

    # ── 关系类型（BaseEra 定义全集，子类可增量）──
    relation_types_base: set[str] = {
        "父子","母子","兄弟","姐妹","夫妻","叔侄","舅甥","祖孙",
        "君臣","臣属","同僚","师生","朋友","敌对","举荐","幕僚","先祖",
    }
    relation_types: set[str]  # 子类 __init__ 中 merge

    # ── 关系类型归一化映射 (LLM输出→规范化) ──
    relation_rt: dict[str, str] = {
        '父子':'子','母子':'子','父':'子','母':'子','子':'父子','女':'女','女兒':'女',
        '兄弟':'兄弟','姐妹':'姐妹',
        '夫妻':'夫妻','第二任妻':'夫妻','第三任妻':'夫妻',
        '祖孙':'祖孙','先祖':'先祖','直系祖先':'先祖',
        '叔侄':'叔侄','舅甥':'舅甥','翁婿':'女婿',
        '君臣':'臣属','臣属':'臣属',
        '同僚':'同僚','朋友':'朋友','敌对':'敌对',
        '师生':'师生','幕僚':'主公','举荐':'被举荐',
        '次子':'子','长子':'子','女婿':'女婿',
    }
    # 关系反向映射
    relation_rev: dict[str, str] = {
        '子':'父子','女':'父子',
        '兄弟':'兄弟','姐妹':'姐妹',
        '夫妻':'夫妻','祖孙':'祖孙','先祖':'先祖',
        '叔侄':'叔侄','舅甥':'舅甥',
        '臣属':'君臣','同僚':'同僚','朋友':'朋友','敌对':'敌对',
        '学生':'师生','主公':'幕僚','被举荐':'举荐',
        '女婿':'翁婿',
    }

    # ── Schema ──
    person_required: list[str] = ["姓名"]
    person_defaults: dict = {
        "字":"无考","号":"无考","朝代":["无考"],
        "生年":None,"卒年":None,
        "出生地":"","出生地今名":"","卒地":"","卒地今名":"",
        "历任势力":[],"官职":[],"爵位":[],"关系":[],"参与事件":[],
        "生平概述":"",
    }
    person_array_fields: list[str] = ["历任势力","官职","爵位","关系","参与事件"]

    # ── 过滤规则 ──
    bad_position_terms: set[str] = {"无考"}
    garbage_names: list[str] = []
    unnamed_patterns: list[str] = [
        r'的(?:娘|妈|母亲|父亲|哥哥|弟弟|姐姐|妹妹|儿子|女儿|孙子|孙女|'
        r'表兄|表弟|表哥|表姐|表妹|干娘|干儿子|嫂子|婆婆|大娘|奶奶|爷|'
        r'姑姑|姑妈|姨妈|舅舅|叔叔|婶婶|女人|男人|师傅|姑娘)$',
        r'媳妇$', r'家的$', r'的女人$', r'的哥哥$', r'的弟弟$', r'的儿子$', r'的母亲$', r'的父亲$',
        r'^两个', r'们$', r'众人$', r'几个', r'其他成员$',
        r'[（(].+[）)]',
    ]
    stub_reject_pattern: str = (
        r'(?:的(?:娘|妈|母亲|父亲|哥哥|弟弟|姐姐|妹妹|儿子|女儿|孙子|孙女|'
        r'表兄|表弟|表哥|表姐|表妹|干娘|干儿子|嫂子|婆婆|大娘|奶奶|爷|'
        r'姑姑|姑妈|姨妈|舅舅|叔叔|婶婶|女人|男人|师傅|姑娘)$'
        r'|媳妇$|家的$|的女人$|的哥哥$|的弟弟$|的儿子$|的母亲$|的父亲$'
        r'|^两个|们$|众人$|几个|其他成员$'
        r'|[（(].+[）)])'
    )

    # ── 别名映射 ──
    aliases: dict[str, str] = {}

    # ── TITLE_FIX (爵号→姓名) ──
    title_fix: dict = {}

    # ── 朝代 stubs ──
    dynasty_stubs: set[str] = set()

    # ── 地名映射 (古称→今名) ──
    place_generic: dict[str, str] = {}

    # ── 事件过滤姓氏 ──
    event_filter_surnames: str = ""

    def __init__(self, book_config: dict, global_config: dict):
        self.bc = book_config
        self.gc = global_config
        self.dynasty = book_config.get("dynasty_name", "")
        # Merge relation types
        self.relation_types = set(self.relation_types_base)
        # Build stub reject regex
        self._stub_reject = re.compile(self.stub_reject_pattern) if self.stub_reject_pattern else None

    # ── 子类可覆盖的方法 ──

    def get_template(self, name: str) -> str:
        """返回模板文件名"""
        mapping = {
            "person": self.template_person,
            "event": self.template_event,
            "place": self.template_place,
            "position": self.template_position,
        }
        return mapping.get(name, f"{name}_template.md")

    def dedup_key(self, person: dict) -> str:
        """去重主键"""
        name = person.get("姓名", "")
        dynasties = person.get("朝代", [])
        dynasty = dynasties[0] if dynasties else "无考"
        return f"{name}|{dynasty}"

    def validate_stub(self, name: str) -> bool:
        """是否应该跳过为这个名称创建 stub"""
        if not name or name in ("无考","","None","none","null","不详"):
            return True
        if self._stub_reject and self._stub_reject.search(name):
            return True
        if any(g in name for g in self.garbage_names):
            return True
        return False

    def extract_places(self, persons: list[dict], events: list[dict]) -> list[dict]:
        """从数据中提取地名节点。子类覆盖。"""
        return []

    def enrich_person(self, person: dict) -> bool:
        """丰富人物数据。返回是否有变更。子类覆盖。"""
        return False

    def _stub(self, name: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "姓名": name,
            "字":"无考","号":"无考","朝代":[],"生年":None,"卒年":None,
            "出生地":"","出生地今名":"","卒地":"","卒地今名":"",
            "历任势力":[],"官职":[],"爵位":[],"关系":[],"参与事件":[],
            "生平概述":"",
            "标签": [self.label, "自动生成stub"],
        }
