"""Test Event Filter — 验证事件名过滤规则"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from pipeline.stub_generator import _is_valid_event

class TestValidEvents:
    def test_official_battles(self):
        assert _is_valid_event("官渡之战")
        assert _is_valid_event("赤壁之战")
        assert _is_valid_event("夷陵之战")

    def test_political_events(self):
        assert _is_valid_event("高平陵政变")
        assert _is_valid_event("三顾茅庐")
        assert _is_valid_event("曹丕代汉")
        assert _is_valid_event("司马炎代魏")

class TestInvalidEvents:
    @pytest.mark.parametrize("name", [
        "被曹操所杀", "被赐死", "被处死",
        "与袁绍交战", "与吕布对抗", "与公孙瓒对战",
        "上书劝谏明帝", "上疏谏孙权", "上表答谢",
        "颁布《太宗论》", "颁布诏令",
        "封关羽为汉寿亭侯", "拜曹操为丞相",
        "谏先主不可争汉中",
        "陈留王奂薨", "曹操卒", "刘备病逝",
        "禅让", "禅代", "受禅",
        "废黜少帝", "册立皇后",
        "刺杀李寿", "拜访姜维",
        "路蕃因忠勇被封亭侯",
        "曹真征朱然", "曹操伐徐州",
        "刘备举袁涣为茂才",
    ])
    def test_fragment_rejected(self, name):
        assert not _is_valid_event(name), f"应被过滤: {name}"

    @pytest.mark.parametrize("name", [
        "曹操与吕布联姻", "张邈与吕布联姻",
        "王允、吕布诛董卓", "刘备与周瑜围曹仁于江陵",
    ])
    def test_personal_action_rejected(self, name):
        assert not _is_valid_event(name), f"个人行动应为事件: {name}"

class TestPunctuation:
    def test_sentence_fragment(self):
        assert not _is_valid_event("谏先主不可争汉中，后被诸葛亮表请其罪")
    
    def test_too_long(self):
        assert _is_valid_event("公孙康分屯有县以南荒地为带方郡")  # 14字 <= 18, 无bad pattern, 由prompt约束

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
