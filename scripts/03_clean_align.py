#!/usr/bin/env python3
"""Step 3: normalize and de-duplicate extracted article sections."""
from __future__ import annotations

import json

from common import CANONICAL, REVIEW, STAGING, normalize_text, sha256, strip_tracking, write_jsonl


def main() -> None:
    raw_path = STAGING / "sections_raw.jsonl"
    if not raw_path.exists():
        raise FileNotFoundError("No extracted sections found; run scripts/02_extract.py first")

    rows = []
    seen: set[tuple[str, str, str]] = set()
    issues = []
    for line_number, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        title = normalize_text(row.get("title", ""))
        text = normalize_text(row.get("text", ""))
        if not title or not text:
            issues.append({"line": line_number, "reason": "empty_title_or_text"})
            continue
        lang = row["lang"]
        dedupe_key = (lang, title.casefold(), text)
        if dedupe_key in seen:
            issues.append({"line": line_number, "reason": "duplicate_section", "title": title})
            continue
        seen.add(dedupe_key)
        canonical_text = f"{title}\n{text}"
        rows.append({
            "id": f"WIKI-BD-{lang}-{len(rows) + 1:04d}",
            "type": "article_section",
            "lang": lang,
            "title": title,
            "text": text,
            "source_url": strip_tracking(row["source_url"]),
            "collected_run": row["collected_run"],
            "content_hash": sha256(canonical_text),
            "metadata": {"verified": False, "review_required": False},
        })

    write_jsonl(CANONICAL / "sections.jsonl", rows)
    write_jsonl(REVIEW / "review_queue.jsonl", issues)
    print(f"[canonical] {len(rows)} article sections -> data/canonical/sections.jsonl")
    if not rows:
        raise RuntimeError("No valid article sections remain after cleaning")


if __name__ == "__main__":
    main()
