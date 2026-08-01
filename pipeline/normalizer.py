"""Phase 4.5: 数据归一化层 —— 渲染前的唯一数据合同"""

import json, re, uuid
from datetime import datetime, timezone

def _s(s):
    s=str(s).strip()
    while s.startswith('[[') and s.endswith(']]'):
        s=s[2:-2]
    return s.strip()

INVAL={'无考','','None','none','null','不详'}

RT={'父子':'子','母子':'子','父':'子','母':'子','子':'父子','女':'父女','兄弟':'兄弟','夫妻':'夫妻','君臣':'臣属','臣属':'臣属','同僚':'同僚','朋友':'朋友','敌对':'敌对','师生':'师生','先祖':'先祖','叔侄':'叔侄','直系祖先':'先祖','第二任妻':'夫妻','第三任妻':'夫妻','次子':'子','长子':'子','女兒':'女','女婿':'女婿'}

REV={'子':'父子','女':'父子','父女':'父子','兄弟':'兄弟','夫妻':'夫妻','臣属':'君臣','朋友':'朋友','敌对':'敌对','先祖':'先祖','叔侄':'叔侄','师生':'学生'}

class Normalizer:
    def __init__(self, book_config, global_config):
        self.bc=book_config
        self.pn=global_config.get('place_normalization',{})
        self.dyn=book_config.get('dynasty_name','')

    def run(self, persons, events):
        print('--- Normalize ---')
        persons=self._strip_all(persons)
        events=self._strip_all(events)
        print('  1. Wikilinks stripped')

        pnames={p['姓名'] for p in persons}
        enames={e['事件名称'] for e in events}

        # Relations
        idx={p['姓名']:p for p in persons}
        for p in persons:
            if '关系' not in p: continue
            for r in p['关系']:
                if not isinstance(r,dict): continue
                rt=r.get('关系类型','')
                if rt in RT: r['关系类型']=RT[rt]
            seen=set();clean=[]
            for r in p['关系']:
                if not isinstance(r,dict): continue
                k=(r.get('人物',''),r.get('关系类型',''))
                if k in seen or not k[0]: continue
                seen.add(k);clean.append(dict(r))
            p['关系']=clean
        # Reverse
        for p in persons:
            for r in p.get('关系',[]):
                t=r.get('人物','');rt=r.get('关系类型','');rv=REV.get(rt)
                if not rv or t not in idx: continue
                tp=idx[t];tp.setdefault('关系',[])
                ex={(x.get('人物',''),x.get('关系类型','')) for x in tp['关系']}
                if (p['姓名'],rv) not in ex:
                    tp['关系'].append({'人物':p['姓名'],'关系类型':rv})
        print('  2. Relations normalized')

        # Event sync
        for p in persons:
            p['参与事件']=[e for e in p.get('参与事件',[]) if str(e) in enames]
        # Event→Person: add stubs for missing participants
        for e in events:
            vp=[]
            for pn in e.get('参与人物',[]):
                pn=_s(str(pn))
                if pn in pnames: vp.append(pn)
                elif pn and pn not in INVAL:
                    pnames.add(pn)
                    persons.append(self._stub(pn));vp.append(pn)
            e['参与人物']=vp
        # Person←Event: add events to participants
        for e in events:
            en=e['事件名称']
            for pn in e.get('参与人物',[]):
                for p in persons:
                    if p['姓名']==pn and en not in p.get('参与事件',[]):
                        p.setdefault('参与事件',[]).append(en)
        print('  3. Event-Person sync')

        # Place normalize in events
        for e in events:
            loc=e.get('地点','')
            if loc in self.pn: e['地点']=self.pn[loc]

        # Filter invalids from link fields
        for p in persons:
            for f in ['出生地今名','卒地今名','出生地','卒地']:
                if p.get(f) in INVAL: p[f]=''
            p['朝代']=[d for d in p.get('朝代',[]) if d not in INVAL]
            p['关系']=[r for r in p.get('关系',[]) if r.get('人物','') not in INVAL]

        # Clean: strip (role) suffixes from relation targets (卞氏(曹丕母) → 卞氏)
        import re as _re
        for p in persons:
            for r in p.get('关系', []):
                tgt = r.get('人物', '')
                if '(' in tgt and ')' in tgt:
                    clean_name = _re.sub(r'\([^)]+\)', '', tgt).strip()
                    if clean_name and clean_name != tgt:
                        r['人物'] = clean_name

        # Pre-step: Ensure all referenced dynasties have stub nodes
        DYNASTIES = {'东汉','西汉','曹魏','蜀汉','东吴','西晋','东晋','倭国'}
        for d in DYNASTIES:
            if d not in pnames:
                pnames.add(d)
                persons.append(self._stub(d))

        # Filter garbage names from person list (compound dynasties, generic titles)
        garbage_patterns = ['-东汉','-曹魏','-蜀汉','-东吴','魏晋','曹魏-','皇帝','群臣','百官','公卿']
        persons = [p for p in persons if not any(g in p.get('姓名','') for g in garbage_patterns)]
        pnames = {p['姓名'] for p in persons}

        # Step: Create stubs for ALL missing relation targets
        for p in persons:
            for r in p.get('关系', []):
                tgt = r.get('人物', '')
                if tgt and tgt not in INVAL and tgt not in pnames:
                    pnames.add(tgt)
                    persons.append(self._stub(tgt))
        print(f'  3.5. Relation stubs: added for missing targets')

        # Final dedup + position name dedup + filter wukao
        for p in persons:
            for f in ['官职','爵位','历任势力']:
                if f not in p: continue
                seen_names=set(); clean=[]
                for item in p[f]:
                    if not isinstance(item,dict): continue
                    name=item.get('名称',item.get('爵名',item.get('势力','')))
                    if name in INVAL or not name: continue
                    n=_s(name)
                    if n not in seen_names:
                        seen_names.add(n)
                        clean.append(item)
                p[f]=clean
            for f in ['参与事件','朝代']:
                if f in p: p[f]=list(dict.fromkeys(p[f]))
            for f in ['关系','官职','爵位','历任势力']:
                if f not in p: continue
                seen=set();clean=[]
                for item in p[f]:
                    key=json.dumps(item,sort_keys=True,ensure_ascii=False)
                    if key not in seen: seen.add(key);clean.append(item)
                p[f]=clean

        # 4.5: Create event stubs for missing event references
        for p in persons:
            for ev in p.get('参与事件', []):
                ev_str = str(ev)
                if ev_str and ev_str not in INVAL and ev_str not in enames:
                    enames.add(ev_str)
                    events.append({
                        'id': str(uuid.uuid4()),
                        '事件名称': ev_str,
                        '时间': '', '朝代': self.dyn, '地点': '',
                        '参与人物': [], '涉及势力': [],
                        '起因': '', '经过': '', '结果': '', '历史意义': '',
                        '出处卷目': '',
                    })
        print(f'  3.7. Event stubs: added for missing events')

        # 5. Post: fix title-as-name (高贵乡公髦→曹髦) + filter non-positions
        TITLE_FIX = {
            '高贵乡公髦': ('曹髦', [{'类型':'谥号','名称':'高贵乡公'}]),
            '陈留王奂': ('曹奂', [{'类型':'爵号','名称':'陈留王'}]),
            '齐王芳': ('曹芳', [{'类型':'爵号','名称':'齐王'}]),
        }
        BAD_POSITIONS = {'夫人', '皇帝', '皇后', '太子', '太后', '王子', '公主', '世子', '无考'}
        for p in persons:
            name = p.get('姓名','')
            if name in TITLE_FIX:
                new_name, altnames = TITLE_FIX[name]
                p['姓名'] = new_name
                p.setdefault('其他名号',[])
                for a in altnames:
                    if a not in p['其他名号']: p['其他名号'].append(a)
            if '官职' in p:
                p['官职'] = [o for o in p['官职'] if o.get('名称','') not in BAD_POSITIONS]
            if '爵位' in p:
                p['爵位'] = [j for j in p['爵位'] if j.get('爵名','') not in BAD_POSITIONS]
        print(f'  5. Title fix + position filter done')
        print(f'  4. Done: {len(persons)} persons, {len(events)} events, {len(pnames)} names')
        return persons, events

    def _strip_all(self, data):
        if isinstance(data,dict): return {k:self._strip_all(v) for k,v in data.items()}
        if isinstance(data,list): return [self._strip_all(i) for i in data]
        if isinstance(data,str): return _s(data)
        return data

    def _stub(self, name):
        return {'id':str(uuid.uuid4()),'姓名':name,'字':'无考','号':'无考','朝代':[],'生年':None,'卒年':None,'出生地':'','出生地今名':'','卒地':'','卒地今名':'','历任势力':[],'官职':[],'爵位':[],'关系':[],'参与事件':[],'生平概述':'','标签':['历史人物','自动生成stub']}
