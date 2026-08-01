"""Test Deduper — 验证跨章去重和碎片名过滤"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from pipeline.deduper import Deduper, _strip_wikilink

@pytest.fixture
def deduper():
    return Deduper({"book_name": "三国志"})

class TestNameFragments:
    def test_single_char_filtered(self, deduper):
        persons = [
            {"姓名":"曹丕","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
            {"姓名":"丕","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
            {"姓名":"叡","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
        {"姓名":"曹叡","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
            {"姓名":"刘备","朝代":["蜀汉"],"字":"","号":"","生年":None,"卒年":None},
        ]
        result = deduper._filter_name_fragments(persons)
        names = {p["姓名"] for p in result}
        assert "丕" not in names
        assert "叡" not in names
        assert "曹丕" in names
        assert "刘备" in names

    def test_three_char_kept(self, deduper):
        persons = [
            {"姓名":"司马懿","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
            {"姓名":"马懿","朝代":["曹魏"],"字":"","号":"","生年":None,"卒年":None},
        ]
        result = deduper._filter_name_fragments(persons)
        names = {p["姓名"] for p in result}
        assert "司马懿" in names
        # 马懿 is 2 chars, substring of 司马懿
        assert "马懿" not in names

class TestCrossChapterDedup:
    def test_same_name_dynasty_merged(self, deduper):
        persons = [
            {"姓名":"诸葛亮","朝代":["蜀汉"],"字":"孔明","号":"","生年":181,"卒年":None,
             "_chapter_index":0,"_chapter_title":"卷三十五"},
            {"姓名":"诸葛亮","朝代":["蜀汉"],"字":"孔明","号":"卧龙","生年":None,"卒年":234,
             "_chapter_index":10,"_chapter_title":"卷十"},
        ]
        result = deduper.deduplicate(persons)
        assert len(result) == 1
        assert result[0]["生年"] == 181
        assert result[0]["卒年"] == 234
        assert result[0]["号"] == "卧龙"

class TestWikilinkStrip:
    def test_strip(self):
        assert _strip_wikilink("[[曹操]]") == "曹操"
        assert _strip_wikilink("曹操") == "曹操"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
