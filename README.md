# Wikipedia Bangladesh Article-to-RAG Pipeline

This project collects the English Wikipedia article at <https://en.wikipedia.org/wiki/Bangladesh>, extracts and cleans its article sections, validates the resulting records, exports RAG chunks, and evaluates retrieval with an editable FAQ-style query set.

The source is an encyclopedia article, not an FAQ page. The crawler does not invent answers or claim its generated evaluation prompts are real customer FAQs. Human-authored FAQ paraphrases should replace the seed queries before interpreting retrieval scores.

## Requirements

- Python 3.10 or later
- Network access to Wikipedia for collection

Install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

The crawler uses Python's standard-library HTTP client; it does not require Playwright or a browser.

## Run the pipeline

From the repository root, collect and process the article:

```powershell
python scripts/01_collect.py
python scripts/02_extract.py
python scripts/03_clean_align.py
python scripts/04_validate.py
python scripts/05_export_rag.py
```

To start only with collection, run `python scripts/01_collect.py`. It checks Wikipedia's `robots.txt`, uses the configured User-Agent and request timeout, and saves the fetched HTML under `data/raw/html/` with a run manifest under `data/raw/manifests/`. If robots access or the article request fails, collection stops with an error instead of silently bypassing the check.

### FAQ-style retrieval evaluation

Generate a seed query file from article section headings:

```powershell
python scripts/06_eval_retrieval.py --make-template
```

Review and rewrite the prompts as natural FAQ questions, add some unanswerable examples with `"expected_doc_id": null`, then save the curated set as `eval/test_questions.jsonl`. Each answerable row uses the following shape:

```json
{"query":"What is Bangladesh's geography like?","lang":"en","expected_doc_id":"<paste-the-matching-doc-id-from-the-export>"}
```

Run the lexical baseline:

```powershell
python scripts/06_eval_retrieval.py --k 5
```

It reports Recall@1/3/5 and MRR for answerable queries, and a simple score-threshold refusal count for unanswerable queries. The template prompts are scaffolding, not a substitute for human-authored FAQ evaluation. Evaluation measures retrieval only, not generated-answer faithfulness.

## Configuration and outputs

`config/sources.yaml` controls the article URL, User-Agent, robots policy, request timeout, and polite delay. The default configuration targets only the requested English Wikipedia page.

- `data/raw/`: immutable timestamped HTML and collection manifests.
- `data/staging/`: extracted sections and review/validation reports.
- `data/canonical/sections.jsonl`: cleaned article section records.
- `data/exports/rag/`: per-language and multilingual JSONL chunks.
- `data/exports/markdown/`: readable per-language article exports.
- `eval/`: generated template and user-curated retrieval questions.

The JSONL export records include chunk/document IDs, language, section heading, text, source URL, collection run, and content hash. Chunk size is configurable with `--max-chars`:

```powershell
python scripts/05_export_rag.py --max-chars 1800
```

Wikipedia content is licensed under the terms linked from Wikipedia; review attribution and license obligations before redistribution or use in a production knowledge base.

## Tests

Run the offline pipeline integration test. It uses synthetic HTML in a temporary directory and makes no network requests:

```powershell
python -m unittest tests.test_pipeline_offline -v
```
