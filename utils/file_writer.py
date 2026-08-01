"""文件写入 —— Jinja2 渲染 + SHA256 幂等写入"""

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


class FileWriter:
    def __init__(self, obsidian_root: str, output_base: str, renderer):
        self.obsidian_root = Path(obsidian_root).expanduser().resolve()
        self.output_base = output_base
        self.renderer = renderer

    def write_person(self, book_config: dict, entity_data: dict) -> tuple[Path, bool]:
        rendered = self.renderer.render_person(entity_data)
        output_dir = self._build_output_dir(book_config, "人物")
        filename = self._make_filename(entity_data.get("姓名", "Unknown"), entity_data.get("朝代", []))
        return self._write_if_changed(output_dir, filename, rendered)

    def write_event(self, book_config: dict, entity_data: dict) -> tuple[Path, bool]:
        rendered = self.renderer.render_event(entity_data)
        output_dir = self._build_output_dir(book_config, "事件")
        filename = self._make_simple_filename(entity_data.get("事件名称", "Unknown"))
        return self._write_if_changed(output_dir, filename, rendered)

    def write_place(self, book_config: dict, entity_data: dict) -> tuple[Path, bool]:
        rendered = self.renderer.render_place(entity_data)
        output_dir = self._build_output_dir(book_config, "地名")
        filename = self._make_simple_filename(entity_data.get("名称", "Unknown"))
        return self._write_if_changed(output_dir, filename, rendered)

    def write_position(self, book_config: dict, entity_data: dict) -> tuple[Path, bool]:
        rendered = self.renderer.render_position(entity_data)
        output_dir = self._build_output_dir(book_config, "职官")
        filename = self._make_simple_filename(entity_data.get("名称", "Unknown"))
        return self._write_if_changed(output_dir, filename, rendered)

    def write_moc(self, book_config: dict, name: str, rendered: str) -> tuple[Path, bool]:
        output_dir = self._build_output_dir(book_config, "MOC")
        filename = self._make_simple_filename(name)
        return self._write_if_changed(output_dir, filename, rendered)

    def _build_output_dir(self, book_config: dict, folder_name: str) -> Path:
        subdir = book_config.get('output_subdir', '')
        if subdir:
            return self.obsidian_root / self.output_base / subdir / folder_name
        return self.obsidian_root / self.output_base / folder_name

    def _make_filename(self, name: str, dynasties: list) -> str:
        safe = re.sub(r'[<>:"/\\|?*]', "-", name)
        return f"{safe}.md"

    def _make_simple_filename(self, name: str) -> str:
        safe = re.sub(r'[<>:"/\\|?*]', "-", name)
        return f"{safe}.md"

    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _write_if_changed(self, directory: Path, filename: str, content: str) -> tuple[Path, bool]:
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / filename
        new_hash = self._compute_hash(content)

        if filepath.exists():
            existing_hash = self._compute_hash(filepath.read_text(encoding="utf-8"))
            if new_hash == existing_hash:
                print(f"  = {filename} (未变)")
                return filepath, False

        filepath.write_text(content, encoding="utf-8")
        print(f"  + {filename}")
        return filepath, True
