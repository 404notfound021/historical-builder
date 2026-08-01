"""源文本分章 —— 正则分章 / 固定长度分块"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chapter:
    index: int
    title: str
    text: str
    source_file: str = ""


class ChapterSplitter:
    def __init__(self, book_config: dict):
        split_cfg = book_config.get("chapter_split", {})
        self.mode = split_cfg.get("mode", "regex")
        self.pattern = split_cfg.get("pattern", "")
        self.chunk_size = split_cfg.get("chunk_size", 3000)
        self.chunk_overlap = split_cfg.get("chunk_overlap", 200)

    def split(self, source_dir: Path) -> list[Chapter]:
        text = self._load_text(source_dir)
        if self.mode == "regex":
            return self._split_by_regex(text)
        elif self.mode == "fixed_chunk":
            return self._split_by_chunk(text)
        else:
            raise ValueError(f"不支持的分章模式: {self.mode}")

    def _load_text(self, source_dir: Path) -> str:
        """加载目录下所有 .txt 文件，自动检测编码"""
        txt_files = sorted(source_dir.glob("*.txt"))
        if not txt_files:
            raise FileNotFoundError(f"{source_dir} 下没有 .txt 文件")
        parts = []
        for f in txt_files:
            raw = f.read_bytes()
            text = self._decode(raw)
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    @staticmethod
    def _decode(raw: bytes) -> str:
        for enc in ["utf-8", "cp936", "gbk", "gb18030", "big5", "utf-16"]:
            try:
                decoded = raw.decode(enc)
                if "\ufffd" not in decoded:
                    return decoded
            except (UnicodeDecodeError, UnicodeError):
                continue
        return raw.decode("utf-8", errors="replace")

    def _split_by_regex(self, text: str) -> list[Chapter]:
        if not self.pattern:
            raise ValueError("regex 模式需要提供 chapter_split.pattern")
        # 统一换行符，避免 \r\n 干扰正则
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        matches = list(re.finditer(self.pattern, text, re.MULTILINE))
        if not matches:
            return [Chapter(index=0, title="全文", text=text.strip())]

        chapters = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            raw_title = m.group().strip()
            raw_text = text[start:end]
            body = re.sub(rf"^{re.escape(raw_title)}[\s\n]*", "", raw_text, count=1)
            chapters.append(Chapter(
                index=i,
                title=raw_title,
                text=body.strip(),
            ))
        return chapters

    def _split_by_chunk(self, text: str) -> list[Chapter]:
        chapters = []
        start = 0
        i = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk = text[start:end]
            chapters.append(Chapter(
                index=i,
                title=f"chunk_{i:04d}",
                text=chunk.strip(),
            ))
            start += self.chunk_size - self.chunk_overlap
            i += 1
        return chapters
