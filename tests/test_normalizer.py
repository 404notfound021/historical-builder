"""Test Normalizer"""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.normalizer import Normalizer, _s

@pytest.fixture
def nz():
    bc = dict(book_name="test", dynasty_name="test")
    gc = dict(place_normalization=dict(洛阳="河南省洛阳市", 建业="南京"))
    return Normalizer(bc, gc)

def make_p(rels=None, events=None, positions=None, dynasty=None, birthplace_pd="", deathplace_pd=""):
    p = dict(id="1", 姓名="test", 字="", 号="", 朝代=dynasty or [], 生年=1, 卒年=2,
             出生地="", 出生地今名=birthplace_pd, 卒地="", 卒地今名=deathplace_pd,
             历任势力=[], 官职=positions or [], 爵位=[], 关系=rels or [],
             参与事件=events or [], 生平概述="", 标签=[])
    return p

class TestStrip:
    def test_normal(self): assert _s("[[曹操]]") == "曹操"
    def test_triple(self): assert _s("[[[[曹操]]]]") == "曹操"
    def test_plain(self): assert _s("曹操") == "曹操"

class TestRelations:
    def test_dedup(self, nz):
        p = [make_p(rels=[dict(人物="曹丕", 关系类型="子"), dict(人物="曹丕", 关系类型="子")])]
        r, _ = nz.run(p, [])
        rels = [(x["人物"], x["关系类型"]) for x in r[0]["关系"]]
        assert rels.count(("曹丕", "子")) == 1 or rels.count(("曹丕", "父子")) == 1

    def test_filter_wukao(self, nz):
        p = [make_p(rels=[dict(人物="无考", 关系类型="同僚")])]
        r, _ = nz.run(p, [])
        assert len(r[0]["关系"]) == 0

    def test_reverse(self, nz):
        p = [make_p(rels=[dict(人物="曹丕", 关系类型="父子")]),
             dict(id="2", 姓名="曹丕", 字="", 号="", 朝代=[], 生年=1, 卒年=2,
                  出生地="", 出生地今名="", 卒地="", 卒地今名="",
                  历任势力=[], 官职=[], 爵位=[], 关系=[], 参与事件=[], 生平概述="", 标签=[])]
        r, _ = nz.run(p, [])
        cao = [x for x in r if x["姓名"]=="test"][0]
        pi = [x for x in r if x["姓名"]=="曹丕"][0]
        assert any(x["人物"]=="曹丕" for x in cao["关系"]), "reverse link should exist"
        assert any(x["人物"]=="test" for x in pi.get("关系",[])), "reverse link should exist"

class TestEventSync:
    def test_clean_invalid(self, nz):
        e = [dict(事件名称="官渡之战", 时间="", 朝代="", 地点="", 参与人物=["test"], 起因="", 经过="", 结果="")]
        p = [make_p(events=["官渡之战", "未知X"])]
        r, _ = nz.run(p, e)
        assert "未知X" not in r[0]["参与事件"]

    def test_stub_for_participants(self, nz):
        e = [dict(事件名称="赤壁", 时间="", 朝代="", 地点="", 参与人物=["周瑜", "黄盖"], 起因="", 经过="", 结果="")]
        r, _ = nz.run([], e)
        names = {p["姓名"] for p in r}
        assert "周瑜" in names
        assert "黄盖" in names

    def test_event_added_to_person(self, nz):
        e = [dict(事件名称="赤壁", 时间="", 朝代="", 地点="", 参与人物=["test"], 起因="", 经过="", 结果="")]
        p = [make_p()]
        r, _ = nz.run(p, e)
        assert "赤壁" in r[0]["参与事件"]

class TestPlaces:
    def test_normalize(self, nz):
        e = [dict(事件名称="x", 时间="", 朝代="", 地点="洛阳", 参与人物=[], 起因="", 经过="", 结果="")]
        _, ev = nz.run([], e)
        assert ev[0]["地点"] == "河南省洛阳市"

class TestInvalFilter:
    def test_dynasty(self, nz):
        p = [make_p(dynasty=["无考", "东汉"])]
        r, _ = nz.run(p, [])
        assert "无考" not in r[0]["朝代"]

    def test_empty_place(self, nz):
        p = [make_p(birthplace_pd="无考", deathplace_pd="无考")]
        r, _ = nz.run(p, [])
        assert r[0]["出生地今名"] == ""
        assert r[0]["卒地今名"] == ""

class TestPositions:
    def test_dedup(self, nz):
        p = [make_p(positions=[dict(名称="丞相", 时段=""), dict(名称="丞相", 时段="221-234")])]
        r, _ = nz.run(p, [])
        names = [o["名称"] for o in r[0]["官职"]]
        assert names.count("丞相") <= 1

    def test_filter_wukao(self, nz):
        p = [make_p(positions=[dict(名称="无考", 时段=""), dict(名称="丞相", 时段="221-234")])]
        r, _ = nz.run(p, [])
        names = [o["名称"] for o in r[0]["官职"]]
        assert "无考" not in names

class TestRelationStubs:
    def test_missing_target_gets_stub(self, nz):
        p = [make_p(rels=[dict(人物="曹琬", 关系类型="子"), dict(人物="曹操", 关系类型="父子")]),
             dict(id="2", 姓名="曹操", 字="", 号="", 朝代=["东汉"], 生年=155, 卒年=220,
                  出生地="", 出生地今名="", 卒地="", 卒地今名="",
                  历任势力=[], 官职=[], 爵位=[], 关系=[], 参与事件=[], 生平概述="", 标签=[])]
        r, _ = nz.run(p, [])
        names = {x["姓名"] for x in r}
        assert "曹琬" in names, "缺失关系目标应自动创建stub"
        assert "曹操" in names

class TestParentheticalClean:
    def test_strip_role_suffix(self, nz):
        p = [make_p(rels=[dict(人物="卞氏(曹丕母)", 关系类型="子")])]
        r, _ = nz.run(p, [])
        targets = {x["人物"] for x in r[0]["关系"]}
        assert "卞氏" in targets
        assert "卞氏(曹丕母)" not in targets
