import csv
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.batch import Batch
from app.models.document import Document

# Comparisons: doc_id -> list of (Comparison, match_filename), best first.
Comparisons = Optional[Dict]


def _pct(value) -> str:
    return f"{value * 100:.1f}%" if value is not None else "—"


def _includes_ai(batch: Batch) -> bool:
    return (batch.analysis_type or "") in ("ai", "both", "mixed")


def _includes_plagiarism(batch: Batch) -> bool:
    return (batch.analysis_type or "plagiarism") in ("plagiarism", "both", "mixed")


def _csv_safe(value) -> str:
    """Stop spreadsheet formula injection from file names (=, +, -, @)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class ReportService:
    """PDF and CSV reports for a batch."""

    @classmethod
    def generate_csv_report(cls, batch: Batch, documents: List[Document], comparisons: Comparisons = None) -> str:
        output = io.StringIO()
        writer = csv.writer(output)

        header = ["Filename", "Status", "Words", "Error"]
        if _includes_ai(batch):
            header += ["AI Score", "AI Verdict", "AI Provider"]
        if comparisons is not None:
            header += ["Max Similarity", "Most Similar Document", "Copied Word-for-Word", "Paraphrased", "Earlier Batch", "Matches Found"]
        writer.writerow(header)

        for doc in documents:
            row = [_csv_safe(doc.filename), doc.status, doc.word_count or "", _csv_safe(doc.error or "")]
            if _includes_ai(batch):
                row += [
                    f"{doc.ai_score:.4f}" if doc.ai_score is not None else "",
                    doc.ai_label or ("AI" if doc.is_ai_generated else "Human"),
                    doc.ai_provider or "",
                ]
            if comparisons is not None:
                doc_comps = comparisons.get(doc.id, [])
                if doc_comps:
                    best, name = max(doc_comps, key=lambda x: x[0].similarity)
                    row += [
                        f"{best.similarity:.4f}",
                        _csv_safe(name),
                        f"{best.lexical_similarity:.4f}" if best.lexical_similarity is not None else "",
                        f"{best.semantic_similarity:.4f}" if best.semantic_similarity is not None else "",
                        "Yes" if best.cross_batch else "No",
                        len(doc_comps),
                    ]
                else:
                    row += ["0", "", "", "", "", 0]
            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def generate_pdf_report(batch: Batch, documents: List[Document], comparisons: Comparisons = None) -> bytes:
        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
            title="Plagiarism and AI analysis report",
        )
        styles = getSampleStyleSheet()
        small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=11)
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11.5)
        quote = ParagraphStyle("quote", parent=small, textColor=colors.HexColor("#374151"))
        P = lambda text, style=cell: Paragraph(escape(str(text)), style)  # noqa: E731

        header_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
        width = A4[0] - 32 * mm

        story = [
            Paragraph("Analysis report", styles["Title"]),
            P(f"Batch: {batch.name or batch.id}", styles["Normal"]),
            P(f"Batch ID: {batch.id}", small),
            P(f"Status: {batch.status}   ·   Checks: {batch.analysis_type or 'plagiarism'}   ·   Documents: {len(documents)}", small),
            P(f"Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", small),
            Spacer(1, 10),
        ]

        # Summary table
        cols = ["Document", "Status"]
        widths = [0.40, 0.14]
        if _includes_ai(batch):
            cols += ["AI score", "AI verdict"]
            widths += [0.11, 0.17]
        if comparisons is not None:
            cols += ["Max similarity"]
            widths += [0.18]
        scale = 1 / sum(widths)
        data = [cols]
        for doc in documents:
            row = [P(doc.filename), P(doc.status)]
            if _includes_ai(batch):
                row += [P(_pct(doc.ai_score) if doc.status == "completed" else "—"),
                        P(doc.ai_label or ("AI" if doc.is_ai_generated else "Human") if doc.status == "completed" else "—")]
            if comparisons is not None:
                doc_comps = comparisons.get(doc.id, [])
                row += [P(_pct(max(c.similarity for c, _ in doc_comps)) if doc_comps else "0%")]
            data.append(row)
        table = Table(data, colWidths=[width * w * scale for w in widths], repeatRows=1)
        table.setStyle(header_style)
        story += [Paragraph("Summary", styles["Heading2"]), table]

        failed = [d for d in documents if d.status == "failed"]
        if failed:
            story += [Spacer(1, 8), Paragraph("Files that could not be analysed", styles["Heading3"])]
            for d in failed:
                story.append(P(f"{d.filename}: {d.error or 'unknown error'}", small))

        # Evidence per document
        if comparisons:
            story += [Spacer(1, 12), Paragraph("Plagiarism matches", styles["Heading2"])]
            any_match = False
            for doc in documents:
                doc_comps = comparisons.get(doc.id, [])
                if not doc_comps:
                    continue
                any_match = True
                block = [Paragraph(escape(doc.filename), styles["Heading3"])]
                rows = [["Similar to", "Overall", "Word-for-word", "Paraphrased", "Source"]]
                for comp, name in doc_comps[:15]:
                    rows.append([
                        P(name), P(_pct(comp.similarity)), P(_pct(comp.lexical_similarity)),
                        P(_pct(comp.semantic_similarity)), P("Earlier batch" if comp.cross_batch else "This batch"),
                    ])
                t = Table(rows, colWidths=[width * x for x in (0.40, 0.13, 0.16, 0.15, 0.16)], repeatRows=1)
                t.setStyle(header_style)
                block.append(t)
                story += block

                top_comp, top_name = doc_comps[0]
                passages = [m for m in (top_comp.matches or []) if m.get("source_chunk")][:5]
                if passages:
                    story.append(Spacer(1, 4))
                    story.append(P(f"Top matching passages with {top_name}:", small))
                    for m in passages:
                        kind = "Exact" if m.get("type") == "exact" else f"Paraphrase ({_pct(m.get('score'))})"
                        story.append(Paragraph(f"<b>{kind}</b> — “{escape(m['source_chunk'][:400])}”", quote))
                        story.append(Spacer(1, 3))
                story.append(Spacer(1, 8))
            if not any_match:
                story.append(P("No significant matches were found.", styles["Normal"]))

        story += [
            Spacer(1, 14),
            Paragraph(
                "Similarity shows how much of a document matches another one, word-for-word or by meaning. "
                "AI scores are estimates, not proof: use them as a prompt for review, never as the sole basis for a decision.",
                small,
            ),
        ]
        pdf.build(story)
        return buffer.getvalue()
