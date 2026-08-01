"""LLM 输出 JSON 解析 + schema 校验 + 自动重试 — era-aware"""
import json, re, uuid


class JsonParseError(Exception):
    def __init__(self, message: str, raw_text: str = ""):
        self.raw_text = raw_text
        super().__init__(message)


class SchemaValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"{field}: {message}")


_SUSPECT_NAME_PATTERNS = [
    r".+[王公侯伯子男]$",
    r"^[某].+[帝王后妃]$",
    r".+[宣文武成景明]$",
    r"^.{1,2}[帝后王]$",
    r".+[太守刺史将军相国]$",
]

def _is_suspect_name(name: str) -> bool:
    for pat in _SUSPECT_NAME_PATTERNS:
        if re.match(pat, name):
            return True
    return False


class JsonParser:
    def __init__(self, era=None):
        """era: BaseEra 实例，提供 schema 和关系类型"""
        self.era = era

    def _valid_relation_types(self) -> set[str]:
        if self.era:
            return self.era.relation_types
        return {"父子","母子","兄弟","姐妹","夫妻","叔侄","舅甥","祖孙",
                "君臣","同僚","师生","朋友","敌对","举荐","幕僚","先祖"}

    def _person_defaults(self) -> dict:
        if self.era:
            return dict(self.era.person_defaults)
        return {
            "字":"无考","号":"无考","朝代":["无考"],
            "生年":None,"卒年":None,
            "出生地":"","出生地今名":"","卒地":"","卒地今名":"",
            "历任势力":[],"官职":[],"爵位":[],"关系":[],"参与事件":[],
            "生平概述":"",
        }

    def _person_array_fields(self) -> set[str]:
        if self.era:
            return set(self.era.person_array_fields)
        return {"历任势力","官职","爵位","关系","参与事件"}

    @staticmethod
    def extract_json(text: str) -> list[dict] | dict:
        if not text or not text.strip():
            raise JsonParseError("LLM 返回空文本")
        cleaned = text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        json_start = None
        for i, ch in enumerate(cleaned):
            if ch in ("[", "{"):
                json_start = i
                break
        if json_start is None:
            raise JsonParseError("未找到 JSON 结构", raw_text=text[:500])
        closer = "]" if cleaned[json_start] == "[" else "}"
        depth = 0
        json_end = None
        for i in range(json_start, len(cleaned)):
            ch = cleaned[i]
            if ch == cleaned[json_start]:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break
        if json_end is None:
            raise JsonParseError("JSON 未闭合", raw_text=text[:500])
        candidate = cleaned[json_start:json_end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise JsonParseError(f"JSON 解析失败: {e}", raw_text=candidate[:500])

    def validate_person(self, data: dict) -> dict:
        if "姓名" not in data or data["姓名"] is None:
            raise SchemaValidationError("姓名", "缺少必需字段 '姓名'")

        defaults = self._person_defaults()
        validated: dict = {"id": str(uuid.uuid4()), "姓名": data["姓名"]}

        for key, default in defaults.items():
            val = data.get(key)
            if val is not None and val != "" and val != []:
                validated[key] = val
            else:
                validated[key] = default

        if not isinstance(validated.get("朝代"), list):
            validated["朝代"] = [validated["朝代"]] if validated["朝代"] != "无考" else ["无考"]

        for field in self._person_array_fields():
            if field not in validated or not isinstance(validated[field], list):
                validated[field] = []

        self._normalize_relations(validated)

        name = validated["姓名"]
        if len(name) <= 2 and not _is_suspect_name(name):
            if name in ("丕","叡","髦","奂","芳","询","懿","亮","羽","飞"):
                validated["_reject"] = True

        if _is_suspect_name(name):
            validated.setdefault("_审核标记", "疑似姓名非本名，请人工确认")

        return validated

    def _normalize_relations(self, person: dict):
        valid_types = self._valid_relation_types()
        cleaned = []
        for rel in person.get("关系", []):
            if not isinstance(rel, dict):
                continue
            target = rel.get("人物", "")
            rtype = rel.get("关系类型", "")
            if not target:
                continue
            if rtype not in valid_types:
                rtype = "同僚"
            cleaned.append({"人物": target, "关系类型": rtype})
        person["关系"] = cleaned

    def parse_with_retry(self, llm_client, system_prompt: str, user_message: str,
                         max_retries: int = 3) -> list[dict]:
        last_error = ""
        for attempt in range(max_retries):
            full_user = user_message
            if last_error:
                full_user = f"{user_message}\n\n[上一轮解析错误，请修正]\n{last_error}"
            raw_response = llm_client.chat_with_retry(system_prompt, full_user)
            if raw_response is None:
                last_error = "LLM 返回 None"
                continue
            try:
                parsed = self.extract_json(raw_response)
            except JsonParseError as e:
                last_error = str(e)
                continue
            if isinstance(parsed, dict):
                parsed = [parsed]
            try:
                return [self.validate_person(p) for p in parsed]
            except SchemaValidationError as e:
                last_error = str(e)
                continue
        raise JsonParseError(f"JSON 解析失败（已重试 {max_retries} 次）: {last_error}")

    @staticmethod
    def validate_event(data: dict) -> dict:
        validated = {
            "id": str(uuid.uuid4()),
            "事件名称": data.get("事件名称", ""),
            "时间": data.get("时间", ""),
            "朝代": data.get("朝代", ""),
            "地点": data.get("地点", ""),
            "参与人物": data.get("参与人物", []),
            "涉及势力": data.get("涉及势力", []),
            "起因": data.get("起因", ""),
            "经过": data.get("经过", ""),
            "结果": data.get("结果", ""),
            "历史意义": data.get("历史意义", ""),
            "出处卷目": data.get("出处卷目", ""),
        }
        if not validated["事件名称"]:
            raise SchemaValidationError("事件名称", "事件名称不能为空")
        return validated

    def parse_event_with_retry(self, llm_client, system_prompt: str, user_message: str,
                               max_retries: int = 3) -> list[dict]:
        last_error = ""
        for attempt in range(max_retries):
            full_user = user_message
            if last_error:
                full_user = f"{user_message}\n\n[上一轮解析错误，请修正]\n{last_error}"
            raw_response = llm_client.chat_with_retry(system_prompt, full_user)
            if raw_response is None:
                last_error = "LLM 返回 None"
                continue
            try:
                parsed = self.extract_json(raw_response)
            except JsonParseError as e:
                last_error = str(e)
                continue
            if isinstance(parsed, dict):
                parsed = [parsed]
            try:
                return [self.validate_event(p) for p in parsed]
            except SchemaValidationError as e:
                last_error = str(e)
                continue
        raise JsonParseError(f"事件 JSON 解析失败（已重试 {max_retries} 次）: {last_error}")
