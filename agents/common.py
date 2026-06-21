from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"


def load_knowledge() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(KNOWLEDGE_DIR.glob("*.md"))
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return value or "generated"


def sentence_case(text: str) -> str:
    text = text.strip(" -:\t")
    return text[:1].upper() + text[1:] if text else text


def read_text_file(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def section_map(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"document": []}
    current = "document"
    for line in markdown.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def bullets(text: str) -> list[str]:
    result = []
    for line in text.splitlines():
        match = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", line)
        if match:
            result.append(sentence_case(match.group(1)))
    return result


def find_section(sections: dict[str, str], *names: str) -> str:
    for wanted in names:
        wanted_lower = wanted.lower()
        for name, body in sections.items():
            if wanted_lower in name:
                return body
    return ""


def split_items(text: str) -> list[str]:
    found = bullets(text)
    if found:
        return found
    parts = re.split(r"[.;]\s+", text.strip())
    return [sentence_case(part) for part in parts if len(part.strip()) > 8]


def summarize(text: str, max_chars: int = 260) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:max_chars].rstrip() + ("..." if len(clean) > max_chars else "")
