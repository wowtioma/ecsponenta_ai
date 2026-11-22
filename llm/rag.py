"""Поиск по базе знаний (ключевыми словами, БЕЗ эмбеддингов).

База маленькая (несколько .md файлов), поэтому эмбеддинги не нужны: они стоят
денег и времени и не дают выигрыша. Ключевой поиск с IDF-ранжированием находит
нужные факты и возвращает цитату «имя файла + раздел» (ТЗ §6, §12.4).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from . import config

_TOKEN_RE = re.compile(r"[a-zа-яё0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """Разбивает markdown на (заголовок-путь, тело). Заголовок — 'h1 › h2 › h3'."""
    sections: list[tuple[str, str]] = []
    title = ""
    h2 = ""
    h3 = ""
    buf: list[str] = []

    def flush() -> None:
        if buf:
            label = " / ".join(x for x in (title, h2, h3) if x)
            sections.append((label, "\n".join(buf).strip()))
            buf.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            flush()
            level = len(m.group(1))
            name = m.group(2).strip()
            if level == 1:
                title, h2, h3 = name, "", ""
            elif level == 2:
                h2, h3 = name, ""
            else:
                h3 = name
        else:
            buf.append(line)
    flush()
    return [(h, t) for h, t in sections if t]


class KnowledgeBase:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else config.SYNONYX_BASE_DIR
        # section = {"file", "section", "text", "terms"}
        self.sections: list[dict] = []
        self._idf: dict[str, float] = {}
        self._index()

    def _index(self) -> None:
        self.sections = []
        for md in sorted(self.base_dir.glob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            for section, body in _parse_sections(text):
                self.sections.append(
                    {
                        "file": md.name,
                        "section": section or md.stem,
                        "text": body,
                        "terms": tokenize(body + " " + section),
                    }
                )
        n = max(len(self.sections), 1)
        df: Counter = Counter()
        for s in self.sections:
            df.update(set(s["terms"]))
        self._idf = {
            t: math.log((n + 1) / (df[t] + 1)) + 1.0 for t in df
        }

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        qterms = set(tokenize(query))
        if not qterms:
            return []
        scored: list[tuple[float, dict]] = []
        for s in self.sections:
            terms = set(s["terms"])
            score = sum(self._idf.get(t, 0.0) for t in qterms if t in terms)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, s in scored[:top_k]:
            out.append(
                {
                    "file": s["file"],
                    "section": s["section"],
                    "text": s["text"],
                    "score": round(score, 4),
                }
            )
        return out

    def cite(self, result: dict) -> str:
        """Цитата для пользователя: «файл, раздел»."""
        return f"{result['file']}, раздел «{result['section']}»"


# Переиспользуемый объект базы (ленивая загрузка при первом обращении).
_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
