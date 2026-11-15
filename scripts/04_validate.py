#!/usr/bin/env python3
"""Step 4: validate canonical article sections before export."""
from __future__ import annotations

import argparse
import re
import sys

from common import CANONICAL, REVIEW, read_jsonl

HTML_LEFTOVER = re.compile(r"</?[a-z][^>]*>", re.I)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail if warnings are found")
    args = parser.parse_args()
    records = read_jsonl(CANONICAL / "sections.jsonl")
    errors: list[str] = []
    warnings: list[str] = []

    if not records:
        errors.append("canonical/sections.jsonl is empty - nothing was extracted")

    seen_ids: set[str] = set()
    seen_sections: set[tuple[str, str]] = set()
    for record in records:
        doc_id = record.get("id", "<missing id>")
        title = record.get("title", "")
        text = record.get("text", "")
        lang = record.get("lang", "")
        source_url = record.get("source_url", "")
        if not doc_id or doc_id in seen_ids:
            errors.append(f"{doc_id}: missing or duplicate document id")
        seen_ids.add(doc_id)
        if not title.strip() or len(text.strip()) < 40:
            errors.append(f"{doc_id}: title is empty or section text is shorter than 40 characters")
        if HTML_LEFTOVER.search(title) or HTML_LEFTOVER.search(text):
            errors.append(f"{doc_id}: HTML tags remain in extracted content")
        if (lang, title.casefold()) in seen_sections:
            warnings.append(f"{doc_id}: duplicate section title for {lang}")
        seen_sections.add((lang, title.casefold()))
        if lang not in ("en", "bn"):
            errors.append(f"{doc_id}: unsupported language {lang!r}")
        if not source_url.startswith("https://"):
            errors.append(f"{doc_id}: missing or invalid HTTPS source URL")
        if "utm_" in source_url:
            errors.append(f"{doc_id}: tracking parameters remain in source URL")
        if not record.get("content_hash"):
            errors.append(f"{doc_id}: missing content hash")

    lines = [
        "# Validation report", "",
        f"Sections: {len(records)}", f"Errors: {len(errors)}", f"Warnings: {len(warnings)}", "",
        "## Errors", *(f"- {error}" for error in errors or ["none"]), "",
        "## Warnings", *(f"- {warning}" for warning in warnings or ["none"]),
    ]
    report_path = REVIEW / "validation_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"errors={len(errors)} warnings={len(warnings)} (details: data/staging/review/validation_report.md)")
    for error in errors[:10]:
        print("  ERROR:", error)
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
