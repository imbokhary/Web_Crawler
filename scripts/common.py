"""Shared helpers for the Wikipedia article knowledge-base pipeline."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "data" / "staging"
CANONICAL = ROOT / "data" / "canonical"
EXPORTS = ROOT / "data" / "exports"
REVIEW = STAGING / "review"
LANGS = ("en", "bn")


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


_NOISE = dict.fromkeys(map(ord, "\u200b\u2060\ufeff\u00ad"), None)
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
_SKIP_SECTIONS = {
    "references", "notes", "further reading", "external links", "see also",
    "bibliography", "sources",
}
_REMOVE_SELECTORS = (
    "script", "style", "noscript", ".mw-editsection", ".reference", ".reflist",
    ".navbox", ".vertical-navbox", ".metadata", ".ambox", ".hatnote", ".toc",
    ".shortdescription", ".noprint", "#catlinks",
)


def normalize_text(text: str) -> str:
    """NFC-normalize text, remove invisible noise, and preserve paragraph breaks."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate(_NOISE).replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def question_key(text: str) -> str:
    text = normalize_text(text).lower().translate(_BN_DIGITS)
    return re.sub(r"[\s\W_]+", " ", text.replace("?", "").replace("\u0964", "")).strip()


def ascii_digits(text: str) -> str:
    return text.translate(_BN_DIGITS)


def strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key not in _TRACKING]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _node_text(node: Tag) -> str:
    for reference in node.select("sup.reference, .mw-ref"):
        reference.decompose()
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([(\\[])\s+", r"\1", text)
    text = re.sub(r"\s+([)\\]])", r"\1", text)
    return normalize_text(text)


def extract_article_sections(html: str) -> list[dict[str, str]]:
    """Extract prose and lists, grouped by article H2 headings, from MediaWiki HTML."""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("#mw-content-text .mw-parser-output")
    if article is None:
        article = soup.select_one("#mw-content-text")
    if article is None:
        raise ValueError("Wikipedia article content was not found (#mw-content-text)")

    infobox = article.select_one("table.infobox")
    infobox_lines = []
    if infobox is not None:
        for row in infobox.select("tr"):
            label_node = row.find("th")
            value_node = row.find("td")
            if label_node is None or value_node is None:
                continue
            label = _node_text(label_node)
            value = _node_text(value_node)
            if label and value:
                infobox_lines.append(f"{label}: {value}")
        infobox.decompose()

    for node in article.select(", ".join(_REMOVE_SELECTORS)):
        node.decompose()

    sections: list[dict[str, str]] = []
    if infobox_lines:
        sections.append({"title": "At a glance", "text": normalize_text("\n".join(infobox_lines))})
    title = "Introduction"
    lines: list[str] = []
    skipped = False

    def save_section() -> None:
        text = normalize_text("\n".join(lines))
        if text:
            sections.append({"title": title, "text": text})

    for node in article.find_all(["h2", "h3", "h4", "p", "li", "blockquote"]):
        if node.name == "p" and node.find_parent("li"):
            continue
        if node.name == "blockquote" and node.find("p"):
            continue
        value = _node_text(node)
        if not value:
            continue
        if node.name == "h2":
            save_section()
            title = value
            skipped = question_key(value) in _SKIP_SECTIONS
            lines = []
        elif skipped:
            continue
        elif node.name in ("h3", "h4"):
            lines.append(f"\n{value}")
        elif node.name == "li":
            lines.append(f"- {value}")
        else:
            lines.append(value)
    save_section()
    if not sections:
        raise ValueError("Wikipedia article contained no extractable prose or list content")
    return sections
