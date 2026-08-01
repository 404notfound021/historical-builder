"""Jinja2 模板渲染"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class TemplateRenderer:
    def __init__(self, template_dir: Path, era=None):
        self.era = era
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _get_template(self, name: str) -> str:
        """优先从 era 获取模板名，fallback 到默认"""
        if self.era:
            return self.era.get_template(name)
        defaults = {"person":"person_template.md","event":"event_template.md",
                     "place":"place_template.md","position":"position_template.md"}
        return defaults.get(name, f"{name}_template.md")

    def render_person(self, data: dict) -> str:
        if self.era:
            data = dict(data)
            data.setdefault("_era_label", self.era.label)
            data.setdefault("_source_heading", self.era.source_heading)
        template = self.env.get_template(self._get_template("person"))
        return template.render(**data)

    def render_event(self, data: dict) -> str:
        if self.era:
            data = dict(data)
            data.setdefault("_era_label", self.era.label)
        template = self.env.get_template(self._get_template("event"))
        return template.render(**data)

    def render_place(self, data: dict) -> str:
        template = self.env.get_template(self._get_template("place"))
        return template.render(**data)

    def render_position(self, data: dict) -> str:
        template = self.env.get_template(self._get_template("position"))
        return template.render(**data)

    def render_moc(self, template_name: str, data: dict) -> str:
        template = self.env.get_template(template_name)
        return template.render(**data)
