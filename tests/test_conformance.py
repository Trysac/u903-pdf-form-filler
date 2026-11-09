"""Conformance test using pdf.js to verify filled AcroForms in CI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pdf_form_filler import fill
from tests.pdfbuild import build_test_pdf


@pytest.mark.conformance
def test_pdfjs_conformance(tmp_path: Path) -> None:
    if not shutil.which("node"):
        pytest.skip("node binary not found")
    pdfjs_path = Path("node_modules/pdfjs-dist/build/pdf.mjs")
    if not pdfjs_path.exists():
        pytest.skip("pdfjs-dist not installed via conformance-setup.sh")

    src = build_test_pdf()
    filled = fill(src, {"name": "Ada", "agree": True, "color": "green"})
    pdf_file = tmp_path / "filled.pdf"
    pdf_file.write_bytes(filled)

    # Script to extract annotations with pdf.js
    node_script = tmp_path / "read_fields.mjs"
    node_script.write_text(
        """
import fs from 'fs';
import * as pdfjs from './node_modules/pdfjs-dist/build/pdf.mjs';

const data = new Uint8Array(fs.readFileSync(process.argv[2]));
const loadingTask = pdfjs.getDocument({ data });
const doc = await loadingTask.promise;
const page = await doc.getPage(1);
const annotations = await page.getAnnotations();
const result = {};
for (const annot of annotations) {
    if (annot.fieldName) {
        result[annot.fieldName] = annot.fieldValue;
    }
}
console.log(JSON.stringify(result));
"""
    )

    proc = subprocess.run(
        ["node", str(node_script), str(pdf_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"node pdf.js execution failed: {proc.stderr}")

    res = json.loads(proc.stdout)
    assert res.get("name") == "Ada"
    assert res.get("color") == "green"
