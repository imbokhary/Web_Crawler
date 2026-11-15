from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OfflinePipelineTest(unittest.TestCase):
    def test_extract_clean_validate_export_and_evaluate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            shutil.copytree(ROOT / "scripts", project / "scripts")
            raw_html = project / "data" / "raw" / "html"
            manifests = project / "data" / "raw" / "manifests"
            raw_html.mkdir(parents=True)
            manifests.mkdir(parents=True)

            repeated_text = "Bangladesh has a diverse landscape shaped by rivers and seasonal rainfall. " * 120
            html = f"""<!doctype html>
            <html><head><title>Bangladesh</title></head><body>
              <h1 id="firstHeading">Bangladesh</h1>
              <div id="mw-content-text"><div class="mw-parser-output">
                <table class="infobox">
                  <tr><th>Capital</th><td>Dhaka</td></tr>
                  <tr><th>Official language</th><td>Bengali</td></tr>
                  <tr><th>Government</th><td>Unitary parliamentary republic</td></tr>
                </table>
                <p>Bangladesh<a> is</a> a country,<b> in South Asia.</b> Its history and people have shaped its modern identity.</p>
                <h2><span class="mw-headline">Geography</span><span class="mw-editsection">[edit]</span></h2>
                <p>{repeated_text}<sup class="reference">[1]</sup></p>
                <h2>References</h2><p>This reference list should not be indexed.</p>
              </div></div>
            </body></html>"""
            html_path = raw_html / "en_offline.html"
            html_path.write_text(html, encoding="utf-8")
            manifest = {
                "run": "offline",
                "entries": [{
                    "key": "en",
                    "lang": "en",
                    "url": "https://en.wikipedia.org/wiki/Bangladesh",
                    "file": html_path.name,
                }],
            }
            manifests.joinpath("offline.json").write_text(json.dumps(manifest), encoding="utf-8")
            manifests.joinpath("latest.json").write_text(json.dumps({"run": "offline"}), encoding="utf-8")

            for script in ("02_extract.py", "03_clean_align.py", "04_validate.py", "05_export_rag.py"):
                result = subprocess.run(
                    [sys.executable, f"scripts/{script}", "--max-chars", "400"]
                    if script == "05_export_rag.py"
                    else [sys.executable, f"scripts/{script}"],
                    cwd=project,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            canonical_path = project / "data" / "canonical" / "sections.jsonl"
            canonical = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["title"] for row in canonical], ["At a glance", "Introduction", "Geography"])
            self.assertIn("Capital: Dhaka", canonical[0]["text"])
            self.assertIn("Bangladesh is a country, in South Asia.", canonical[1]["text"])
            self.assertNotIn("This reference list", "\n".join(row["text"] for row in canonical))

            exported = project / "data" / "exports" / "rag" / "multilingual.jsonl"
            chunks = [json.loads(line) for line in exported.read_text(encoding="utf-8").splitlines()]
            self.assertGreater(len(chunks), len(canonical))
            self.assertTrue(all(len(chunk["text"]) <= 400 for chunk in chunks))

            template_result = subprocess.run(
                [sys.executable, "scripts/06_eval_retrieval.py", "--make-template"],
                cwd=project,
                capture_output=True,
                text=True,
            )
            self.assertEqual(template_result.returncode, 0, template_result.stdout + template_result.stderr)
            eval_dir = project / "eval"
            shutil.copyfile(eval_dir / "test_questions.template.jsonl", eval_dir / "test_questions.jsonl")
            with (eval_dir / "test_questions.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps({
                    "query": "unrelated query with no matching article",
                    "lang": "en",
                    "expected_doc_id": None,
                }) + "\n")

            evaluation = subprocess.run(
                [sys.executable, "scripts/06_eval_retrieval.py"],
                cwd=project,
                capture_output=True,
                text=True,
            )
            self.assertEqual(evaluation.returncode, 0, evaluation.stdout + evaluation.stderr)
            self.assertIn("Recall@1=", evaluation.stdout)
            self.assertIn("unanswerable=1", evaluation.stdout)


if __name__ == "__main__":
    unittest.main()
