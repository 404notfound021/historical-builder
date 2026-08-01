"""Phase 4.5: 数据归一化层 —— 渲染前的唯一数据合同"""
import json, re, uuid
from datetime import datetime, timezone

def _s(s):
    s=str(s).strip()
    while s.startswith('[[') and s.endswith(']]'): s=s[2:-2]
    return s.strip()

INVAL={'无考','','None','none','null','不详'}

# ── Base relation maps (universal, all eras) ──
BASE_RT={
    '父子':'子','母子':'子','父':'子','母':'子','子':'父子','女':'女','女兒':'女',
    '兄弟':'兄弟','姐妹':'姐妹',
    '夫妻':'夫妻','第二任妻':'夫妻','第三任妻':'夫妻',
    '祖孙':'祖孙','先祖':'先祖','直系祖先':'先祖',
    '叔侄':'叔侄','舅甥':'舅甥',
    '君臣':'臣属','臣属':'臣属',
    '同僚':'同僚','朋友':'朋友','敌对':'敌对',
    '师生':'师生','幕僚':'主公','举荐':'被举荐',
    '次子':'子','长子':'子','女婿':'女婿',
}
BASE_REV={
    '子':'父子','女':'父子',
    '兄弟':'兄弟','姐妹':'姐妹',
    '夫妻':'夫妻','祖孙':'祖孙','先祖':'先祖',
    '叔侄':'叔侄','舅甥':'舅甥',
    '臣属':'君臣','同僚':'同僚','朋友':'朋友','敌对':'敌对',
    '学生':'师生','主公':'幕僚','被举荐':'举荐',
    '女婿':'岳婿',
}

# ── Literary enrichment ──
LITERARY_RT={
    '恋人':'恋人',
    '主仆':'仆从',
    '妾室':'妾室',
    '姑侄':'姑侄',
    '姨甥':'姨甥',
    '表亲':'表亲',
    '妯娌':'妯娌',
    '连襟':'连襟',
    '堂亲':'堂亲',
    '养父子':'子','养母子':'子',
}
LITERARY_REV={
    '恋人':'恋人',
    '仆从':'主仆',
    '妾室':'妾室',
    '姑侄':'姑侄',
    '姨甥':'姨甥',
    '表亲':'表亲',
    '妯娌':'妯娌',
    '连襟':'连襟',
    '堂亲':'堂亲',
}

# ── Era-aware constants ──
ANCIENT_TITLE_FIX={
    '高贵乡公髦':('曹髦',[{'类型':'谥号','名称':'高贵乡公'}]),
    '陈留王奂':('曹奂',[{'类型':'爵号','名称':'陈留王'}]),
    '齐王芳':('曹芳',[{'类型':'爵号','名称':'齐王'}]),
}
ANCIENT_DYNASTIES={'东汉','西汉','曹魏','蜀汉','东吴','西晋','东晋','倭国'}
ANCIENT_PLACE_GENERIC={'吴地':'扬州','蜀地':'益州','魏地':'中原','秦地':'关中'}
ANCIENT_GARBAGE=['-东汉','-曹魏','-蜀汉','-东吴','魏晋','曹魏-','皇帝','群臣','百官','公卿','位宫']

ANCIENT_BAD_POS={'夫人','皇帝','皇后','太子','太后','王子','公主','世子','无考'}
LITERARY_BAD_POS={'无考'}  # literary: only filter placeholder values

class Normalizer:
    def __init__(self, book_config, global_config):
        self.bc=book_config
        self.gc=global_config
        self.pn=global_config.get('place_normalization',{})
        self.dyn=book_config.get('dynasty_name','')
        self.era=book_config.get('era','ancient')

        # Build effective RT/REV: base + era enrichment
        self.RT=dict(BASE_RT)
        self.REV=dict(BASE_REV)
        if self.era=='literary':
            self.RT.update(LITERARY_RT)
            self.REV.update(LITERARY_REV)

        # Era-aware filter sets
        self.bad_pos=LITERARY_BAD_POS if self.era=='literary' else ANCIENT_BAD_POS
        self.title_fix=ANCIENT_TITLE_FIX
        self.dynasty_stubs=ANCIENT_DYNASTIES
        self.place_generic=ANCIENT_PLACE_GENERIC
        self.garbage_names=ANCIENT_GARBAGE

        # Era filters from config (override bad_position_terms)
        era_cfg=global_config.get('era_filters',{}).get(self.era,{})
        self.bad_terms=era_cfg.get('bad_position_terms',[])

    def run(self, persons, events):
        print('--- Normalize ---')
        persons=self._strip_all(persons)
        events=self._strip_all(events)
        print('  1. Wikilinks stripped')
        pnames={p['姓名'] for p in persons}
        enames={e['事件名称'] for e in events}
        idx={p['姓名']:p for p in persons}

        # Relations: type normalize + dedup + reverse
        for p in persons:
            if '关系' not in p: continue
            for r in p['关系']:
                if not isinstance(r,dict): continue
                rt=r.get('关系类型','')
                if rt in self.RT: r['关系类型']=self.RT[rt]
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
                t=r.get('人物','');rt=r.get('关系类型','');rv=self.REV.get(rt)
                if not rv or t not in idx: continue
                tp=idx[t];tp.setdefault('关系',[])
                ex={(x.get('人物',''),x.get('关系类型','')) for x in tp['关系']}
                if (p['姓名'],rv) not in ex:
                    tp['关系'].append({'人物':p['姓名'],'关系类型':rv})
        print('  2. Relations normalized')

        # Event sync
        for p in persons:
            p['参与事件']=[e for e in p.get('参与事件',[]) if str(e) in enames]
        # Event->Person stubs
        for e in events:
            vp=[]
            for pn in e.get('参与人物',[]):
                pn=_s(str(pn))
                if pn in pnames: vp.append(pn)
                elif pn and pn not in INVAL:
                    pnames.add(pn);persons.append(self._stub(pn));vp.append(pn)
            e['参与人物']=vp
        # Person<-Event reverse
        for e in events:
            en=e['事件名称']
            for pn in e.get('参与人物',[]):
                for p in persons:
                    if p['姓名']==pn and en not in p.get('参与事件',[]):
                        p.setdefault('参与事件',[]).append(en)

        # Place normalize + clean
        for e in events:
            loc=e.get('地点','')
            loc=re.sub(r'[（(].+?[）)]','',loc).strip()
            loc=re.sub(r'之[南北东西]$','',loc)
            if loc in self.pn: e['地点']=self.pn[loc]
            else: e['地点']=loc
        # Generic place mapping (ancient only)
        if self.era=='ancient':
            for e in events:
                loc=e.get('地点','')
                if loc in self.place_generic: e['地点']=self.place_generic[loc]

        print('  3. Event-Person sync')

        # Filter invalids
        for p in persons:
            for f in ['出生地今名','卒地今名','出生地','卒地']:
                if p.get(f) in INVAL: p[f]=''
            p['朝代']=[d for d in p.get('朝代',[]) if d not in INVAL]
            p['关系']=[r for r in p.get('关系',[]) if r.get('人物','') not in INVAL]

        # Era-aware position filter
        if self.bad_terms:
            for p in persons:
                if '官职' in p:
                    p['官职']=[o for o in p['官职'] if not any(t in o.get('名称','') for t in self.bad_terms)]

        # Position/peerage name dedup
        for p in persons:
            for f in ['官职','爵位','历任势力']:
                if f not in p: continue
                seen_n=set();clean=[]
                for item in p[f]:
                    if not isinstance(item,dict): continue
                    n=item.get('名称',item.get('爵名',item.get('势力','')))
                    if n in INVAL or not n: continue
                    if n not in seen_n: seen_n.add(n);clean.append(item)
                p[f]=clean

        # Final dedup
        for p in persons:
            for f in ['参与事件','朝代']:
                if f in p: p[f]=list(dict.fromkeys(p[f]))
            for f in ['关系','官职','爵位','历任势力']:
                if f not in p: continue
                seen=set();clean=[]
                for item in p[f]:
                    key=json.dumps(item,sort_keys=True,ensure_ascii=False)
                    if key not in seen: seen.add(key);clean.append(item)
                p[f]=clean

        # Title fix (ancient only)
        for p in persons:
            name=p.get('姓名','')
            if name in self.title_fix:
                nn,alt=self.title_fix[name];p['姓名']=nn
                p.setdefault('其他名号',[])
                for a in alt:
                    if a not in p['其他名号']: p['其他名号'].append(a)
            if '官职' in p: p['官职']=[o for o in p['官职'] if o.get('名称','') not in self.bad_pos]
            if '爵位' in p: p['爵位']=[j for j in p['爵位'] if j.get('爵名','') not in self.bad_pos]

        # Merge persons with same name after TITLE_FIX rename
        nidx={}
        for i,p in enumerate(persons):
            nm=p['姓名']
            if nm in nidx:
                persons[nidx[nm]]=self._merge_person(persons[nidx[nm]],p)
                persons[i]=None
            else:
                nidx[nm]=i
        persons=[p for p in persons if p is not None]
        pnames={p['姓名'] for p in persons}

        # Dynasty stubs (ancient only)
        if self.era=='ancient':
            for d in self.dynasty_stubs:
                if d not in pnames: pnames.add(d);persons.append(self._stub(d))

        # Filter garbage names
        persons=[p for p in persons if not any(g in p.get('姓名','') for g in self.garbage_names)]
        pnames={p['姓名'] for p in persons}

        # Relation stub targets
        for p in persons:
            for r in p.get('关系',[]):
                tgt=r.get('人物','')
                tgt=re.sub(r'\([^)]+\)','',tgt).strip()
                r['人物']=tgt
                if tgt and tgt not in INVAL and tgt not in pnames:
                    pnames.add(tgt);persons.append(self._stub(tgt))

        # Event stub targets
        for p in persons:
            for ev in p.get('参与事件',[]):
                if str(ev) not in enames:
                    enames.add(str(ev))
                    events.append({'id':str(uuid.uuid4()),'事件名称':str(ev),'时间':'','朝代':self.dyn,'地点':'','参与人物':[],'涉及势力':[],'起因':'','经过':'','结果':'','历史意义':'','出处卷目':''})

        print(f'  4. Done: {len(persons)} persons, {len(events)} events')
        return persons, events

    def _strip_all(self, data):
        if isinstance(data,dict): return {k:self._strip_all(v) for k,v in data.items()}
        if isinstance(data,list): return [self._strip_all(i) for i in data]
        if isinstance(data,str): return _s(data)
        return data

    def _stub(self, name):
        return {'id':str(uuid.uuid4()),'姓名':name,'字':'无考','号':'无考','朝代':[],'生年':None,'卒年':None,'出生地':'','出生地今名':'','卒地':'','卒地今名':'','历任势力':[],'官职':[],'爵位':[],'关系':[],'参与事件':[],'生平概述':'','标签':['历史人物','自动生成stub']}

    def _merge_person(self, base, other):
        """合并两个同名人物，other 的数据补入 base（base 优先）"""
        for f in ['字','号','出生地','出生地今名','卒地','卒地今名','生平概述']:
            if not base.get(f) or base[f]=='无考':
                v=other.get(f)
                if v and v!='无考': base[f]=v
        for f in ['生年','卒年']:
            if not base.get(f) and other.get(f):
                base[f]=other[f]
        for lst in ['官职','爵位','历任势力','关系','参与事件','朝代','标签']:
            base.setdefault(lst,[])
            for item in other.get(lst,[]):
                if item not in base[lst]:
                    base[lst].append(item)
        if other.get('其他名号'):
            base.setdefault('其他名号',[])
            for a in other['其他名号']:
                if a not in base['其他名号']: base['其他名号'].append(a)
        if other.get('各卷记载'):
            base.setdefault('各卷记载','')
            if base['各卷记载']: base['各卷记载']+='\n'+other['各卷记载']
            else: base['各卷记载']=other['各卷记载']
        return base
