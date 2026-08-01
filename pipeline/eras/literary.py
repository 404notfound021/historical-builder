"""LiteraryEra — 文学作品 era (红楼梦等)"""
import re
from pipeline.eras.base import BaseEra

class LiteraryEra(BaseEra):
    label = "文学人物"
    source_type = "文学"

    def __init__(self, book_config, global_config):
        super().__init__(book_config, global_config)

        # ── 关系类型: base + literary enrichment ──
        self.relation_types = self.relation_types_base | {
            "恋人","主仆","妾室","姑侄","姨甥","表亲","妯娌","连襟","堂亲",
        }

        # ── 关系归一化: base + literary ──
        self.relation_rt = dict(self.relation_rt)
        self.relation_rt.update({
            '恋人':'恋人','主仆':'仆从','妾室':'妾室',
            '姑侄':'姑侄','姨甥':'姨甥','表亲':'表亲',
            '妯娌':'妯娌','连襟':'连襟','堂亲':'堂亲',
            '养父子':'子','养母子':'子',
        })

        # ── 关系反向映射: base + literary ──
        self.relation_rev = dict(self.relation_rev)
        self.relation_rev.update({
            '恋人':'恋人','仆从':'主仆','妾室':'妾室',
            '姑侄':'姑侄','姨甥':'姨甥','表亲':'表亲',
            '妯娌':'妯娌','连襟':'连襟','堂亲':'堂亲',
        })

        # ── 过滤规则 ──
        self.bad_position_terms = {"无考"}
        self.garbage_names = []

        # ── 别名映射 ──
        self.aliases = {
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

        # ── 主仆关系 fixup: 同僚→主仆/妾室/恋人 ──
        self.servants = {
            '袭人','晴雯','麝月','紫鹃','雪雁','秋纹','碧痕','鸳鸯','平儿','司棋',
            '侍书','入画','莺儿','翠缕','翠墨','素云','彩云','彩霞','彩屏','彩明',
            '玉钏儿','金钏儿','小红','佳蕙','坠儿','四儿','春燕','芳官','藕官',
            '蕊官','豆官','葵官','艾官','药官','龄官','文官','茄官','宝珠','瑞珠',
            '绣鸾','绣凤','绣橘','小螺','丰儿','隆儿','兴儿','昭儿','焙茗','茗烟',
            '锄药','墨雨','焦大','赖大','赖二','赖升','林之孝','吴新登','来旺',
            '旺儿','门子','小鹊','傻大姐','鲍二','包勇','李贵',
            '周瑞家的','林之孝家的','王善保家的','赖大家的','赖嬷嬷',
            '柳家的','柳嫂儿','玉柱儿媳妇','玉柱儿家的','吴兴家的','郑华家的',
            '来旺家的','来喜家的','张材家的','宋妈妈','宋嬷嬷','李嬷嬷',
            '赵嬷嬷','王嬷嬷','李妈','老祝妈','叶妈','夏婆子','周妈妈',
            '芳官干娘','春燕的娘','春燕的姑妈','坠儿母亲','司棋的母亲',
            '宝蟾','善姐','银蝶','同喜','同贵','智能儿',
        }
        self.concubines = {'赵姨娘','周姨娘','尤二姐','秋桐','佩凤','文花'}
        self.concubine_husbands = {
            '赵姨娘':'贾政','周姨娘':'贾政',
            '尤二姐':'贾琏','秋桐':'贾琏',
            '佩凤':'贾珍','文花':'贾珍',
        }
        self.known_lovers = {('贾宝玉','林黛玉'), ('林黛玉','贾宝玉')}

    def dedup_key(self, person):
        """文学人物按姓名+首次出现的家族去重"""
        name = person.get("姓名", "")
        factions = person.get("历任势力", [])
        faction = factions[0].get("势力","") if factions else ""
        return f"{name}|{faction}"

    def fix_relations(self, persons):
        """将 LLM 误分类的'同僚'修正为正确的文学关系类型"""
        from collections import Counter
        stats = Counter()
        person_map = {p['姓名']: p for p in persons}

        for p in persons:
            if '关系' not in p: continue
            for r in p['关系']:
                if not isinstance(r, dict): continue
                if r.get('关系类型','') != '同僚': continue

                target = r.get('人物','')
                source = p['姓名']
                new_type = None

                # Known lover pairs
                if (source, target) in self.known_lovers:
                    new_type = '恋人'
                # Source is servant → 主仆 (source serves target)
                elif source in self.servants:
                    new_type = '主仆'
                # Target is servant, source is not → 仆从
                elif target in self.servants and source not in self.servants:
                    new_type = '仆从'
                # Concubine → husband
                elif source in self.concubines and target == self.concubine_husbands.get(source, ''):
                    new_type = '妾室'
                # Husband → concubine
                elif target in self.concubines and source == self.concubine_husbands.get(target, ''):
                    new_type = '妾室'

                if new_type and new_type != '同僚':
                    r['关系类型'] = new_type
                    stats[f'同僚→{new_type}'] += 1

        print(f"  Relation fixup: {sum(stats.values())} corrected")
        return persons

    def extract_places(self, persons, events):
        """文学地名: 从事件地点提取虚构地名"""
        place_events = {}
        place_persons = {}

        if events:
            for e in events:
                loc = (e.get('地点','') or '').strip()
                if not loc or loc == '无考': continue
                ename = e.get('事件名称','')
                place_events.setdefault(loc, []).append(ename)
                for pn in e.get('参与人物',[]):
                    place_persons.setdefault(loc, set()).add(str(pn))

        for p in persons:
            for field in ['出生地','卒地']:
                val = p.get(field,'')
                if val and val != '无考':
                    place_persons.setdefault(val, set()).add(p['姓名'])

        return place_events, place_persons
