#!/usr/bin/env python3
"""Step 1: collect source HTML for configured Wikipedia article pages."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen

from common import RAW, load_config, now_iso, sha256, write_json


def fetch(url: str, user_agent: str, timeout: int, require_html: bool = True) -> tuple[str, int, str]:
    request = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if require_html and content_type != "text/html":
                raise ValueError(f"{url} returned unexpected content type: {content_type}")
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace"), response.status, response.geturl()
    except URLError as exc:
        raise RuntimeError(f"Unable to fetch {url}: {exc}") from exc


def robots_allows(url: str, user_agent: str, timeout: int) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    text, _, _ = fetch(robots_url, user_agent, timeout, require_html=False)
    parser = RobotFileParser(robots_url)
    parser.parse(text.splitlines())
    return parser.can_fetch(user_agent, url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=("en", "bn"), help="collect one configured language")
    args = parser.parse_args()

    config = load_config()
    crawl = config["crawl"]
    pages = config["pages"]
    targets = [(lang, url) for lang, url in pages.items() if not args.lang or args.lang == lang]
    if not targets:
        parser.error(f"no configured page for language {args.lang!r}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    html_dir = RAW / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    (RAW / "manifests").mkdir(parents=True, exist_ok=True)
    entries = []

    for index, (lang, url) in enumerate(targets):
        if crawl["respect_robots"] and not robots_allows(url, crawl["user_agent"], crawl["timeout_seconds"]):
            print(f"[skip] robots.txt disallows {url}")
            continue
        print(f"[collect] {lang}: {url}")
        html, status, final_url = fetch(url, crawl["user_agent"], crawl["timeout_seconds"])
        if status != 200:
            raise RuntimeError(f"Unexpected HTTP status {status} for {url}")
        path = html_dir / f"{lang}_{timestamp}.html"
        path.write_text(html, encoding="utf-8")
        entries.append({
            "key": lang,
            "lang": lang,
            "url": final_url,
            "file": path.name,
            "fetched_at": now_iso(),
            "http_status": status,
            "html_sha256": sha256(html),
            "html_bytes": len(html.encode("utf-8")),
        })
        if index + 1 < len(targets):
            time.sleep(crawl["delay_seconds"])

    if not entries:
        raise RuntimeError("No pages were collected; check robots.txt permissions and configuration")
    write_json(RAW / "manifests" / f"{timestamp}.json", {"run": timestamp, "entries": entries})
    write_json(RAW / "manifests" / "latest.json", {"run": timestamp})
    print(f"[done] run {timestamp}; collected {len(entries)} page(s)")


if __name__ == "__main__":
    main()
