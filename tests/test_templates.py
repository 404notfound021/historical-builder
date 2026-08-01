"""Test Template rendering — 验证模板输出不含 [[无考]]、无双括号等"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pipeline.template_renderer import TemplateRenderer
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "resource" / "templates"

@pytest.fixture
def renderer():
    return TemplateRenderer(TEMPLATE_DIR)

@pytest.fixture
def base_person():
    return {
        "id": "test-uuid", "姓名": "测试", "字": "子测", "号": "无考",
        "朝代": ["东汉"], "生年": 100, "卒年": 200,
        "出生地": "沛国谯县", "出生地今名": "安徽省亳州市",
        "卒地": "洛阳", "卒地今名": "河南省洛阳市",
        "历任势力": [{"势力": "曹魏", "时段": "200-220", "角色": "将军"}],
        "官职": [{"名称": "丞相", "时段": "210-220"}, {"名称": "无考", "时段": ""}],
        "爵位": [{"爵名": "魏王", "册封时间": "216"}],
        "关系": [{"人物": "曹操", "关系类型": "父子"}, {"人物": "曹丕", "关系类型": "兄弟"}],
        "参与事件": ["官渡之战", "赤壁之战"],
        "生平概述": "测试人物", "各卷记载": "",
        "出处史书": "三国志", "出处卷目": "卷十五",
        "创建时间": "2026-01-01", "修改时间": "2026-01-01",
        "标签": ["历史人物"],
    }

class TestPersonTemplate:
    def test_no_wukao_wikilink(self, renderer, base_person):
        """渲染后不应出现 [[无考]]"""
        result = renderer.render_person(base_person)
        assert "[[无考]]" not in result, "不应出现 [[无考]] wikilink"
        assert "[[None]]" not in result, "不应出现 [[None]]"

    def test_no_double_brackets(self, renderer, base_person):
        """不应出现三层以上括号"""
        result = renderer.render_person(base_person)
        assert "[[[[" not in result, "不应出现四层括号"
        assert "]]]]" not in result

    def test_body_table_has_wikilinks(self, renderer, base_person):
        """body表格里的人物应有 [[wikilink]]"""
        result = renderer.render_person(base_person)
        # Body table: | 子 | [[曹操]] |
        assert "| 子 | [[曹操]]" in result or "| 父子 | [[曹操]]" in result, "body表格应有wikilink"

    def test_events_have_wikilinks(self, renderer, base_person):
        result = renderer.render_person(base_person)
        assert "[[官渡之战]]" in result

    def test_faction_has_wikilink(self, renderer, base_person):
        result = renderer.render_person(base_person)
        assert "[[曹魏]]" in result

    def test_position_has_wikilink(self, renderer, base_person):
        result = renderer.render_person(base_person)
        assert "[[丞相]]" in result

    def test_wukao_position_not_rendered(self, renderer, base_person):
        """无考的官职不应出现在表格中"""
        result = renderer.render_person(base_person)
        # Count 丞相 occurrences (frontmatter + body table)
        assert result.count("丞相") >= 2, "丞相应该出现"
        # 无考 should only appear once (for 号字段), not in position table
        frontmatter_end = result.index("---", result.index("---")+1)
        body = result[frontmatter_end:]
        # Body table shouldn't have 无考 as a position link
        assert "[[无考]]" not in body

    def test_empty_dynasty_not_linked(self, renderer):
        """空朝代或无考不应包wikilink"""
        p = {
            "id":"x","姓名":"x","字":"","号":"","朝代":["无考"],"生年":None,"卒年":None,
            "出生地":"","出生地今名":"无考","卒地":"","卒地今名":"无考",
            "历任势力":[],"官职":[],"爵位":[],"关系":[],"参与事件":[],"生平概述":"",
            "出处史书":"","出处卷目":"","创建时间":"","修改时间":"","标签":[]
        }
        result = renderer.render_person(p)
        assert "[[无考]]" not in result

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
