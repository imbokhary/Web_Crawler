#!/usr/bin/env python3
"""Step 5: export validated article sections as bounded RAG chunks."""
from __future__ import annotations

import argparse

from common import CANONICAL, EXPORTS, read_jsonl, write_jsonl

MAX_CHARS = 1800


def split_text(text: str, max_chars: int) -> list[str]:
    if max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    remaining = text.strip()
    chunks = []
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        boundary = remaining.rfind(" ", 0, max_chars + 1)
        if boundary <= 0:
            boundary = max_chars
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    args = parser.parse_args()
    if args.max_chars < 1:
        parser.error("--max-chars must be a positive integer")

    records = read_jsonl(CANONICAL / "sections.jsonl")
    if not records:
        raise FileNotFoundError("No canonical sections found; run scripts/02_extract.py through 04_validate.py first")

    by_lang: dict[str, list[dict]] = {}
    for record in records:
        prefix = f"{record['title']}\n"
        body_limit = args.max_chars - len(prefix)
        if body_limit < 1:
            raise ValueError(f"--max-chars is too small for section title {record['title']!r}")
        pieces = split_text(record["text"], body_limit)
        for number, piece in enumerate(pieces, 1):
            by_lang.setdefault(record["lang"], []).append({
                "id": f"{record['id']}#{number}",
                "doc_id": record["id"],
                "lang": record["lang"],
                "section_title": record["title"],
                "text": f"{prefix}{piece}",
                "source_url": record["source_url"],
                "collected_run": record["collected_run"],
                "content_hash": record["content_hash"],
                "verified": record["metadata"]["verified"],
                "review_required": record["metadata"]["review_required"],
            })

    for lang, documents in by_lang.items():
        write_jsonl(EXPORTS / "rag" / f"{lang}.jsonl", documents)
        lines = [
            f"# Bangladesh Wikipedia article ({lang})", "",
            "Extracted from the cited Wikipedia article. Review source content and licensing before reuse.", "",
        ]
        for document in documents:
            lines.extend([
                f"## {document['section_title']}", "", document["text"].split("\n", 1)[1], "",
                f"_Source: {document['source_url']} | document: {document['doc_id']}_", "",
            ])
        markdown_path = EXPORTS / "markdown" / f"article_{lang}.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text("\n".join(lines), encoding="utf-8")

    multilingual = [document for docs in by_lang.values() for document in docs]
    write_jsonl(EXPORTS / "rag" / "multilingual.jsonl", multilingual)
    longest = max(len(document["text"]) for document in multilingual)
    print(f"exported {len(multilingual)} chunks across {len(by_lang)} language(s); longest chunk: {longest} chars")


if __name__ == "__main__":
    main()
