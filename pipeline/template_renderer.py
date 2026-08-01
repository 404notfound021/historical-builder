"""Jinja2 模板渲染"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class TemplateRenderer:
    def __init__(self, template_dir: Path):
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=False,
            lstrip_blocks=True,
        )

    def render_person(self, data: dict) -> str:
        template = self.env.get_template("person_template.md")
        return template.render(**data)

    def render_event(self, data: dict) -> str:
        template = self.env.get_template("event_template.md")
        return template.render(**data)

    def render_place(self, data: dict) -> str:
        template = self.env.get_template("place_template.md")
        return template.render(**data)

    def render_position(self, data: dict) -> str:
        template = self.env.get_template("position_template.md")
        return template.render(**data)

    def render_moc(self, template_name: str, data: dict) -> str:
        template = self.env.get_template(template_name)
        return template.render(**data)
