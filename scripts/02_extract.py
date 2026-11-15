#!/usr/bin/env python3
"""Step 2: extract article sections from the latest raw collection."""
from __future__ import annotations

import json

from common import RAW, STAGING, extract_article_sections, write_json, write_jsonl


def main() -> None:
    manifests = RAW / "manifests"
    latest_path = manifests / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError("No collection found; run scripts/01_collect.py first")
    run = json.loads(latest_path.read_text(encoding="utf-8"))["run"]
    manifest_path = manifests / f"{run}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    report = {"run": run, "pages": {}}

    for entry in manifest["entries"]:
        html_path = RAW / "html" / entry["file"]
        html = html_path.read_text(encoding="utf-8")
        sections = extract_article_sections(html)
        page_rows = []
        for order, section in enumerate(sections, 1):
            page_rows.append({
                **section,
                "lang": entry["lang"],
                "order": order,
                "source_url": entry["url"],
                "collected_run": run,
            })
        rows.extend(page_rows)
        report["pages"][entry["lang"]] = {
            "url": entry["url"],
            "sections_extracted": len(page_rows),
        }
        print(f"[{entry['lang']}] extracted {len(page_rows)} article sections")

    write_jsonl(STAGING / "sections_raw.jsonl", rows)
    write_json(STAGING / "review" / "extract_report.json", report)
    if not rows:
        raise RuntimeError("No article sections were extracted")


if __name__ == "__main__":
    main()
