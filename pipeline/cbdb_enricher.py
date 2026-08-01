"""CBDB 数据补全 —— 用中国历代人物传记数据库填补 LLM 漏掉的字段

数据源: CBDB SQLite (66万人物, 30K地名, 56万亲属, 59万官职)
"""

import sqlite3
from pathlib import Path


# 简→繁映射
_S2T = str.maketrans({
    "门": "門", "马": "馬", "风": "風", "韦": "韋", "云": "雲",
    "长": "長", "见": "見", "贝": "貝", "车": "車", "东": "東",
    "乐": "樂", "冯": "馮", "卢": "盧", "刘": "劉", "关": "關",
    "孙": "孫", "张": "張", "杨": "楊", "郑": "鄭", "赵": "趙",
    "诸": "諸", "葛": "葛", "亮": "亮", "备": "備", "飞": "飛",
    "羽": "羽", "曹": "曹", "操": "操", "权": "權", "坚": "堅",
    "策": "策", "绍": "紹", "术": "術", "表": "表",
})


def _to_traditional(s: str) -> str:
    return s.translate(_S2T) if s else s


class CBDBEnricher:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn: sqlite3.Connection | None = None

    def _connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    # ================================================================
    # 人物查询与补全
    # ================================================================

    def query_person(self, name: str) -> dict | None:
        self._connect()
        trad = _to_traditional(name)

        row = self.conn.execute("""
            SELECT DISTINCT b.c_personid, b.c_name_chn, b.c_birthyear, b.c_deathyear,
                   b.c_index_year, b.c_female, b.c_dy, d.c_dynasty_chn
            FROM BIOG_MAIN b
            LEFT JOIN DYNASTIES d ON b.c_dy = d.c_dy
            WHERE b.c_name_chn = ? OR b.c_name_chn = ?
               OR b.c_personid IN (SELECT c_personid FROM ALTNAME_DATA WHERE c_alt_name_chn = ?)
            ORDER BY CASE WHEN d.c_dynasty_chn LIKE '%三國%' THEN 1
                          WHEN d.c_dynasty_chn = '東漢' THEN 2 ELSE 3 END
            LIMIT 1
        """, (trad, name, trad)).fetchone()

        if not row:
            return None

        pid = row["c_personid"]
        result = {
            "cbdb_id": pid,
            "姓名(繁)": row["c_name_chn"],
            "生年": self._or_none(row["c_birthyear"]),
            "卒年": self._or_none(row["c_deathyear"]),
            "索引年": row["c_index_year"],
            "性别": "女" if row["c_female"] else "男",
            "朝代": row["c_dynasty_chn"] or "",
        }

        # 1. 别名
        result["别名详情"] = self._query_altnames(pid)
        # 2. 地址 + 坐标
        result["地址"] = self._query_addresses(pid)
        # 3. 亲属
        result["亲属"] = self._query_kinship(pid)
        # 4. 官职
        result["官职"] = self._query_offices(pid)
        # 5. 入仕途径
        result["入仕"] = self._query_entries(pid)
        # 6. 社会机构
        result["社会机构"] = self._query_institutions(pid)

        return result

    def _query_altnames(self, pid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT c_alt_name_chn, c_name_type_desc_chn FROM View_AltnameData WHERE c_personid = ?",
            (pid,)
        ).fetchall()
        return [{"名称": r["c_alt_name_chn"], "类型": r["c_name_type_desc_chn"] or ""} for r in rows]

    def _query_addresses(self, pid: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT v.c_addr_chn, v.c_addr_desc_chn, v.c_firstyear, v.c_lastyear,
                   a.x_coord, a.y_coord, a.c_admin_type
            FROM View_BiogAddrData v
            LEFT JOIN ADDR_CODES a ON v.c_addr_id = a.c_addr_id
            WHERE v.c_personid = ?
        """, (pid,)).fetchall()
        result = []
        for r in rows:
            entry = {"地名": r["c_addr_chn"], "类型": r["c_addr_desc_chn"] or ""}
            if r["x_coord"] and r["y_coord"] and abs(r["x_coord"]) > 0.01:
                entry["坐标"] = f"{r['y_coord']:.4f}, {r['x_coord']:.4f}"
            if r["c_admin_type"]:
                entry["行政级别"] = r["c_admin_type"]
            result.append(entry)
        return result

    def _query_kinship(self, pid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT c_kin_chn, c_kinrel_chn FROM View_KinAddrData WHERE c_personid = ?",
            (pid,)
        ).fetchall()
        return [{"人物": r["c_kin_chn"], "关系": r["c_kinrel_chn"] or ""} for r in rows]

    def _query_offices(self, pid: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT o.c_office_chn, p.c_firstyear, p.c_lastyear
            FROM POSTED_TO_OFFICE_DATA p
            JOIN OFFICE_CODES o ON p.c_office_id = o.c_office_id
            WHERE p.c_personid = ? ORDER BY p.c_firstyear
        """, (pid,)).fetchall()
        return [{"名称": r["c_office_chn"], "始年": r["c_firstyear"], "终年": r["c_lastyear"]} for r in rows]

    def _query_entries(self, pid: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT ec.c_entry_desc_chn, e.c_year
            FROM ENTRY_DATA e
            JOIN ENTRY_CODES ec ON e.c_entry_code = ec.c_entry_code
            WHERE e.c_personid = ?
        """, (pid,)).fetchall()
        return [{"途径": r["c_entry_desc_chn"], "年份": r["c_year"]} for r in rows]

    def _query_institutions(self, pid: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT DISTINCT sinc.c_inst_name_hz
            FROM BIOG_INST_DATA bid
            JOIN SOCIAL_INSTITUTION_NAME_CODES sinc ON bid.c_inst_name_code = sinc.c_inst_name_code
            WHERE bid.c_personid = ?
            LIMIT 10
        """, (pid,)).fetchall()
        return [{"机构": r["c_inst_name_hz"]} for r in rows]

    def enrich_person(self, person: dict) -> dict:
        name = person.get("姓名", "")
        if not name:
            return person

        cbdb = self.query_person(name)
        if not cbdb:
            return person

        # --- 生卒年 ---
        if not person.get("生年") and cbdb.get("生年"):
            person["生年"] = cbdb["生年"]
        if not person.get("卒年") and cbdb.get("卒年"):
            person["卒年"] = cbdb["卒年"]
        if not person.get("卒年") and person.get("生年") and cbdb.get("卒年"):
            person["卒年"] = cbdb["卒年"]

        # --- 字 ---
        for alt in cbdb.get("别名详情", []):
            t = alt.get("类型", "")
            if "字" in t and not alt["名称"].startswith("第"):
                person.setdefault("字", alt["名称"])
                break

        # --- 号 ---
        for alt in cbdb.get("别名详情", []):
            t = alt.get("类型", "")
            if ("號" in t or "号" in t or "別號" in t or "室名" in t):
                person.setdefault("号", alt["名称"])
                break

        # --- 谥号/庙号 ---
        for alt in cbdb.get("别名详情", []):
            t = alt.get("类型", "")
            if "諡" in t or "廟" in t or "封爵" in t:
                person.setdefault("其他名号", [])
                exists = any(n.get("名称") == alt["名称"] for n in person["其他名号"])
                if not exists:
                    person["其他名号"].append({"类型": t, "名称": alt["名称"]})

        # --- 出生地/卒地 ---
        for addr in cbdb.get("地址", []):
            atype = addr.get("类型", "")
            aname = addr.get("地名", "")
            coord = addr.get("坐标", "")
            if not aname:
                continue
            if "籍貫" in atype or "出生" in atype:
                if not person.get("出生地") or person["出生地"] == "无考":
                    person["出生地"] = aname
                if coord and (not person.get("出生地坐标")):
                    person["出生地坐标"] = coord
            if "葬" in atype or "死" in atype:
                if not person.get("卒地") or person["卒地"] == "无考":
                    person["卒地"] = aname
                if coord and (not person.get("卒地坐标")):
                    person["卒地坐标"] = coord

        # --- 亲属 ---
        exist_kins = {(r.get("人物", ""), r.get("关系类型", "")) for r in person.get("关系", [])}
        for kin in cbdb.get("亲属", []):
            kname = kin.get("人物", "")
            krel = kin.get("关系", "")
            if not kname or not krel:
                continue
            if (kname, krel) not in exist_kins:
                person.setdefault("关系", []).append({"人物": kname, "关系类型": krel})

        # --- 官职 ---
        exist_offices = {o.get("名称", "") for o in person.get("官职", [])}
        for off in cbdb.get("官职", []):
            oname = off.get("名称", "")
            if oname and oname not in exist_offices:
                period = f"{off['始年']}-{off.get('终年', '')}" if off.get("始年") else ""
                person.setdefault("官职", []).append({"名称": oname, "时段": period})

        # --- 入仕途径（新）---
        for entry in cbdb.get("入仕", []):
            tujing = entry.get("途径", "")
            if tujing and tujing != "未詳":
                person.setdefault("入仕途径", []).append(tujing)

        # --- 社会机构（新）---
        for inst in cbdb.get("社会机构", []):
            iname = inst.get("机构", "")
            if iname:
                person.setdefault("关联机构", []).append(iname)

        # --- 朝代标准化 ---
        cbdb_dynasty = cbdb.get("朝代", "")
        if cbdb_dynasty and (not person.get("朝代") or person["朝代"] == ["无考"]):
            person["朝代"] = [cbdb_dynasty]

        person["cbdb_id"] = cbdb["cbdb_id"]
        return person

    # ================================================================
    # 地名独立查询 —— 坐标 + 沿革
    # ================================================================

    def query_place(self, name: str, dynasty: str = "") -> dict | None:
        """查询地名，返回带坐标和时期范围的记录"""
        self._connect()

        row = self.conn.execute("""
            SELECT c_name_chn, c_firstyear, c_lastyear, x_coord, y_coord,
                   c_admin_type, CHGIS_PT_ID, c_alt_names
            FROM ADDR_CODES
            WHERE c_name_chn = ?
            ORDER BY CASE WHEN x_coord != 0 AND y_coord != 0 THEN 0 ELSE 1 END,
                     c_firstyear
            LIMIT 1
        """, (name,)).fetchone()

        if not row:
            return None

        return {
            "名称": row["c_name_chn"],
            "始年": row["c_firstyear"],
            "终年": row["c_lastyear"],
            "坐标": f"{row['y_coord']:.4f}, {row['x_coord']:.4f}" if row["x_coord"] and abs(row["x_coord"]) > 0.01 else "",
            "行政级别": row["c_admin_type"] or "",
            "chgis_id": row["CHGIS_PT_ID"],
            "别名": row["c_alt_names"] or "",
        }

    def search_places(self, name_fragment: str, limit: int = 20) -> list[dict]:
        """模糊搜索地名"""
        self._connect()
        rows = self.conn.execute("""
            SELECT c_name_chn, c_firstyear, c_lastyear, x_coord, y_coord, c_admin_type
            FROM ADDR_CODES
            WHERE c_name_chn LIKE ?
            ORDER BY c_firstyear
            LIMIT ?
        """, (f"%{name_fragment}%", limit)).fetchall()

        results = []
        for r in rows:
            results.append({
                "名称": r["c_name_chn"],
                "始年": r["c_firstyear"],
                "终年": r["c_lastyear"],
                "坐标": f"{r['y_coord']:.4f}, {r['x_coord']:.4f}" if r["x_coord"] and abs(r["x_coord"]) > 0.01 else "",
                "行政级别": r["c_admin_type"] or "",
            })
        return results

    @staticmethod
    def _or_none(val):
        return val if val else None
