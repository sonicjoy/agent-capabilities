#!/usr/bin/env python3
"""Generate pool settlement post-mortem DOCX from JSON data.

Usage:
  python generate_postmortem_docx.py --data postmortem-data.json --output Pool-Post-Mortem.docx

Requires: pip install python-docx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def set_cell_shading(cell, fill_hex: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill_hex)
    cell._tc.get_or_add_tcPr().append(shading)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], header_fill: str = "D9E2F3") -> None:
    if not headers:
        return
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    hdr_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        hdr_cells[i].text = str(header)
        set_cell_shading(hdr_cells[i], header_fill)
        for p in hdr_cells[i].paragraphs:
            for run in p.runs:
                run.bold = True
    for row in rows:
        row_cells = table.add_row().cells
        for i, value in enumerate(row):
            row_cells[i].text = str(value)
    doc.add_paragraph()


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        doc.add_paragraph(str(item), style="List Bullet")


def add_numbered(doc: Document, items: list[str]) -> None:
    for item in items:
        doc.add_paragraph(str(item), style="List Number")


def add_section_table(doc: Document, section: dict) -> None:
    if section.get("title"):
        doc.add_heading(section["title"], level=section.get("level", 2))
    if section.get("paragraphs"):
        for text in section["paragraphs"]:
            doc.add_paragraph(str(text))
    if section.get("bold_paragraphs"):
        for item in section["bold_paragraphs"]:
            p = doc.add_paragraph()
            p.add_run(f"{item['label']}: ").bold = True
            p.add_run(str(item["text"]))
    if section.get("table"):
        t = section["table"]
        add_table(doc, t.get("headers", []), t.get("rows", []))
    if section.get("bullets"):
        add_bullets(doc, section["bullets"])
    if section.get("numbered"):
        add_numbered(doc, section["numbered"])
    if section.get("code"):
        p = doc.add_paragraph(str(section["code"]))
        p.runs[0].font.name = "Consolas"
        p.runs[0].font.size = Pt(10)


def build_document(data: dict) -> Document:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    pool_id = data.get("pool_id", "UNKNOWN")
    title = doc.add_heading(data.get("title", f"Post-Mortem: Pool {pool_id} Wrong Settlement"), 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if data.get("subtitle"):
        subtitle = doc.add_paragraph(data["subtitle"])
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle.runs[0].italic = True

    meta = data.get("meta", {})
    if meta:
        mp = doc.add_paragraph()
        for key, value in meta.items():
            mp.add_run(f"{key}: ").bold = True
            mp.add_run(f"{value}\n")

    for section in data.get("sections", []):
        level = section.get("level", 1)
        if section.get("heading"):
            doc.add_heading(section["heading"], level=level)
        add_section_table(doc, section)

    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pool settlement post-mortem DOCX")
    parser.add_argument("--data", required=True, help="Path to postmortem JSON file")
    parser.add_argument("--output", required=True, help="Output .docx path")
    args = parser.parse_args()

    data_path = Path(args.data)
    output_path = Path(args.output)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    doc = build_document(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(output_path)


if __name__ == "__main__":
    main()
