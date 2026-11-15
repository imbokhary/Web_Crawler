#!/usr/bin/env python3
"""Step 6: evaluate FAQ-style queries against exported article chunks."""
from __future__ import annotations

import argparse
import importlib
import math
import re
import sys
from collections import Counter

from common import EXPORTS, ROOT, ascii_digits, normalize_text, read_jsonl, write_jsonl

PUNCT = re.compile(r"[\s,.:;!?()\[\]{}\"'\u2018\u2019\u201c\u201d\u0964\-\u2013\u2014/]+")


def features(text: str) -> Counter[str]:
    tokens = [token for token in PUNCT.split(ascii_digits(normalize_text(text)).lower()) if token]
    result: Counter[str] = Counter(tokens)
    for token in tokens:
        if len(token) > 3:
            result.update(token[index:index + 3] for index in range(len(token) - 2))
    return result


class LexicalRetriever:
    def __init__(self, documents: list[dict]):
        self.documents = documents
        self.vectors = [features(document["text"]) for document in documents]
        document_frequency = Counter(
            feature for vector in self.vectors for feature in vector.keys()
        )
        document_count = len(documents)
        self.idf = {
            feature: math.log((document_count + 1) / (count + 0.5)) + 1
            for feature, count in document_frequency.items()
        }
        self.norms = [self._norm(vector) for vector in self.vectors]

    def _norm(self, vector: Counter[str]) -> float:
        return math.sqrt(sum((count * self.idf.get(feature, 1)) ** 2 for feature, count in vector.items())) or 1.0

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        query_vector = features(query)
        query_norm = self._norm(query_vector)
        scores: dict[str, float] = {}
        for document, vector, norm in zip(self.documents, self.vectors, self.norms):
            score = sum(
                count * self.idf.get(feature, 1) * vector.get(feature, 0) * self.idf.get(feature, 1)
                for feature, count in query_vector.items()
            ) / (query_norm * norm)
            doc_id = document["doc_id"]
            scores[doc_id] = max(scores.get(doc_id, 0.0), score)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]


def make_template() -> int:
    documents = read_jsonl(EXPORTS / "rag" / "multilingual.jsonl")
    if not documents:
        print("No exported RAG chunks found; run scripts/05_export_rag.py first")
        return 1
    seen: set[str] = set()
    rows = []
    for document in documents:
        doc_id = document["doc_id"]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        rows.append({
            "query": f"What does the article say about {document['section_title']}?",
            "lang": document["lang"],
            "expected_doc_id": doc_id,
            "note": "Replace with a human-authored FAQ/paraphrase; add unanswerable examples with expected_doc_id=null.",
        })
    output = ROOT / "eval" / "test_questions.template.jsonl"
    write_jsonl(output, rows)
    print(f"wrote {output.relative_to(ROOT)} ({len(rows)} seed queries; review and paraphrase before interpreting scores)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retriever", help="module:function returning ordered document IDs")
    parser.add_argument("--make-template", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--refuse-below", type=float, default=0.15)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")
    if not 0 <= args.refuse_below <= 1:
        parser.error("--refuse-below must be between 0 and 1")
    if args.make_template:
        return make_template()

    tests = read_jsonl(ROOT / "eval" / "test_questions.jsonl")
    if not tests:
        print("eval/test_questions.jsonl is empty - create it from --make-template and curate the queries")
        return 1

    if args.retriever:
        module_name, function_name = args.retriever.split(":", 1)
        retrieve = getattr(importlib.import_module(module_name), function_name)

        def ranked(query: str) -> tuple[list[str], float | None]:
            return retrieve(query, args.k), None
    else:
        documents = read_jsonl(EXPORTS / "rag" / "multilingual.jsonl")
        if not documents:
            print("No exported RAG chunks found; run scripts/05_export_rag.py first")
            return 1
        retriever = LexicalRetriever(documents)

        def ranked(query: str) -> tuple[list[str], float | None]:
            results = retriever.search(query, args.k)
            return [doc_id for doc_id, _ in results], results[0][1] if results else 0.0

    hit_counts = {1: 0, 3: 0, 5: 0}
    reciprocal_rank = 0.0
    answerable = 0
    unanswerable = 0
    refusal_correct = 0
    by_lang: dict[str, list[int]] = {}
    misses = []
    for test in tests:
        query = test["query"]
        expected = test["expected_doc_id"]
        ids, top_score = ranked(query)
        if expected is None:
            unanswerable += 1
            if top_score is not None:
                refusal_correct += top_score < args.refuse_below
            continue
        answerable += 1
        rank = ids.index(expected) + 1 if expected in ids else None
        for cutoff in hit_counts:
            hit_counts[cutoff] += bool(rank and rank <= cutoff)
        reciprocal_rank += 1 / rank if rank else 0
        by_lang.setdefault(test.get("lang", "?"), []).append(int(bool(rank and rank <= 5)))
        if not rank or rank > 1:
            misses.append((query, expected, ids[:3]))

    if not answerable:
        print("No answerable evaluation queries found")
        return 1
    scores = "  ".join(f"Recall@{cutoff}={count / answerable:.2f}" for cutoff, count in hit_counts.items())
    print(f"answerable={answerable}  {scores}  MRR={reciprocal_rank / answerable:.2f}")
    for lang, values in by_lang.items():
        print(f"  {lang}: Recall@5={sum(values) / len(values):.2f} (n={len(values)})")
    if unanswerable and args.retriever:
        print(f"unanswerable={unanswerable} (custom retriever does not return scores; refusal not measured)")
    elif unanswerable:
        print(f"unanswerable={unanswerable}  correctly below threshold: {refusal_correct}")
    for query, expected, got in misses[:10]:
        print(f"  miss: {query!r} expected {expected}, got {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
