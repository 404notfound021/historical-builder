"""红楼梦关系修正器 v3 — 极端保守策略，只修正确认无误的"""
import json
from collections import Counter

# 已知丫鬟/仆人（千人级别手工标注）
SERVANTS = {
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

# 已知妾室
CONCUBINES = {'赵姨娘','周姨娘','尤二姐','秋桐','佩凤','文花'}
# 妾室的丈夫（用于定向妾室关系）
CONCUBINE_HUSBANDS = {
    '赵姨娘': '贾政', '周姨娘': '贾政',
    '尤二姐': '贾琏', '秋桐': '贾琏',
    '佩凤': '贾珍', '文花': '贾珍',
}

# 恋人（极其精确）
KNOWN_LOVERS = {('贾宝玉','林黛玉'), ('林黛玉','贾宝玉')}

# 丫鬟的主人映射（已知已知的主人）
SERVANT_MASTERS = {
    '袭人': '贾宝玉', '晴雯': '贾宝玉', '麝月': '贾宝玉',
    '秋纹': '贾宝玉', '碧痕': '贾宝玉', '芳官': '贾宝玉',
    '四儿': '贾宝玉', '小红': '贾宝玉', '佳蕙': '贾宝玉',
    '焙茗': '贾宝玉', '茗烟': '贾宝玉', '锄药': '贾宝玉',
    '李嬷嬷': '贾宝玉', '李贵': '贾宝玉',
    '紫鹃': '林黛玉', '雪雁': '林黛玉', '王嬷嬷': '林黛玉',
    '莺儿': '薛宝钗', '文杏': '薛宝钗',
    '平儿': '王熙凤', '丰儿': '王熙凤', '隆儿': '王熙凤',
    '兴儿': '贾琏', '昭儿': '贾琏', '旺儿': '贾琏',
    '司棋': '贾迎春', '绣橘': '贾迎春',
    '侍书': '贾探春', '翠墨': '贾探春',
    '入画': '贾惜春', '彩屏': '贾惜春',
    '翠缕': '史湘云',
    '素云': '李纨',
    '宝珠': '秦可卿', '瑞珠': '秦可卿',
    '鸳鸯': '贾母', '琥珀': '贾母', '珍珠': '贾母',
    '金钏儿': '王夫人', '玉钏儿': '王夫人', '彩云': '王夫人', '彩霞': '王夫人',
    '绣鸾': '王夫人', '绣凤': '王夫人',
    '宝蟾': '夏金桂',
    '智能儿': '水月庵',  # 小尼姑
}

def fix_relations(persons: list[dict]) -> tuple[list[dict], Counter]:
    stats = Counter()
    person_set = {p['姓名'] for p in persons}

    for p in persons:
        if '关系' not in p:
            continue
        for r in p['关系']:
            if not isinstance(r, dict):
                continue
            rel_type = r.get('关系类型', '')
            target = r.get('人物', '')
            source = p['姓名']

            if rel_type != '同僚':
                continue

            new_type = None

            # Rule 1: known lovers
            if (source, target) in KNOWN_LOVERS:
                new_type = '恋人'

            # Rule 2: source is known servant → 主仆 (此人服侍对方)
            elif source in SERVANTS:
                new_type = '主仆'

            # Rule 3: target is known servant, source is not → 仆从 (对方服侍此人)
            elif target in SERVANTS and source not in SERVANTS:
                new_type = '仆从'

            # Rule 4: concubine→husband
            elif source in CONCUBINES and target == CONCUBINE_HUSBANDS.get(source, ''):
                new_type = '妾室'

            # Rule 5: husband→concubine (reverse direction)
            elif target in CONCUBINES and source == CONCUBINE_HUSBANDS.get(target, ''):
                new_type = '妾室'

            if new_type and new_type != '同僚':
                old = r['关系类型']
                r['关系类型'] = new_type
                stats[f'{old}→{new_type}'] += 1
                stats['total_fixed'] += 1

    return persons, stats

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'output/红楼梦/intermediate/merged_persons.json'

    with open(path) as f:
        persons = json.load(f)

    before = Counter()
    for p in persons:
        for r in p.get('关系', []):
            if isinstance(r, dict):
                before[r.get('关系类型','')] += 1

    persons, stats = fix_relations(persons)

    after = Counter()
    for p in persons:
        for r in p.get('关系', []):
            if isinstance(r, dict):
                after[r.get('关系类型','')] += 1

    print(f"Before: {dict(before.most_common(15))}")
    print(f"After:  {dict(after.most_common(20))}")
    print(f"Fixes:  {dict(stats)}")

    with open(path, 'w') as f:
        json.dump(persons, f, ensure_ascii=False, indent=2)

    print("\n=== Verification ===")
    for name in ['贾宝玉','袭人','林黛玉','赵姨娘','尤二姐','晴雯','紫鹃']:
        for p in persons:
            if p['姓名'] == name:
                rels = {}
                for r in p.get('关系', []):
                    rt = r.get('关系类型','')
                    tgt = r.get('人物','')
                    rels.setdefault(rt, []).append(tgt)
                print(f"\n{name}:")
                for rt, tgts in sorted(rels.items()):
                    unique = list(dict.fromkeys(tgts))
                    print(f"  {rt}: {', '.join(unique[:10])}{' ...' if len(unique)>10 else ''}")
                break
