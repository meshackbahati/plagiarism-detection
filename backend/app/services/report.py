import csv
import io
from typing import List, Dict, Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.models.document import Document
from app.models.batch import Batch
from app.models.comparison import Comparison


class ReportService:
    """Service for generating reports (PDF, CSV)"""

    @classmethod
    def generate_csv_report(
        cls,
        batch: Batch,
        documents: List[Document],
        comparisons: Optional[Dict] = None,
    ) -> str:
        """
        Generate CSV report for a batch.

        Args:
            batch: The batch object.
            documents: List of documents in the batch.
            comparisons: Dict mapping doc_id -> list of (Comparison, match_filename) tuples.
                         If None, plagiarism columns are omitted.
        """
        output = io.StringIO()
        writer = csv.writer(output)

        has_plagiarism = comparisons is not None

        # Header
        header = ['Filename', 'Status', 'AI Score', 'Is AI Generated']
        if has_plagiarism:
            header.extend(['Max Plagiarism Match', 'Most Similar Document'])
        writer.writerow(header)

        # Build a lookup: doc_id -> list of (comparison, match_filename)
        comp_lookup = comparisons or {}

        for doc in documents:
            row = [
                doc.filename,
                doc.status,
                f"{doc.ai_score:.2f}" if doc.ai_score is not None else "N/A",
                "Yes" if doc.is_ai_generated else "No",
            ]

            if has_plagiarism:
                doc_comps = comp_lookup.get(doc.id, [])
                if doc_comps:
                    # Find the highest similarity match
                    best = max(doc_comps, key=lambda x: x[0].similarity)
                    row.append(f"{best[0].similarity:.2f}")
                    row.append(best[1])
                else:
                    row.append("N/A")
                    row.append("N/A")

            writer.writerow(row)

        return output.getvalue()

    @staticmethod
    def generate_pdf_report(
        batch: Batch,
        documents: List[Document],
        comparisons: Optional[Dict] = None,
    ) -> bytes:
        """
        Generate PDF report for a batch.

        Args:
            batch: The batch object.
            documents: List of documents in the batch.
            comparisons: Dict mapping doc_id -> list of (Comparison, match_filename) tuples.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = styles['Title']
        story.append(Paragraph(f"Analysis Report", title_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Batch: {batch.id}", styles['Normal']))
        story.append(Paragraph(f"Status: {batch.status}", styles['Normal']))
        story.append(Paragraph(f"Analysis Type: {batch.analysis_type or 'N/A'}", styles['Normal']))
        story.append(Spacer(1, 24))

        # AI Detection Table
        story.append(Paragraph("AI Detection Results", styles['Heading2']))
        story.append(Spacer(1, 8))

        ai_data = [['Filename', 'Status', 'AI Score', 'Verdict']]
        for doc_item in documents:
            score = f"{doc_item.ai_score:.1%}" if doc_item.ai_score is not None else "N/A"
            verdict = "AI-Generated" if doc_item.is_ai_generated else "Human-Written"
            if doc_item.ai_score is None:
                verdict = "N/A"

            ai_data.append([doc_item.filename, doc_item.status, score, verdict])

        ai_table = Table(ai_data)
        ai_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4338ca')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f3ff')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(ai_table)

        # Plagiarism Table (if comparison data available)
        if comparisons:
            story.append(Spacer(1, 24))
            story.append(Paragraph("Plagiarism Results", styles['Heading2']))
            story.append(Spacer(1, 8))

            plag_data = [['Document', 'Most Similar To', 'Similarity']]
            has_any = False
            for doc_item in documents:
                doc_comps = comparisons.get(doc_item.id, [])
                if doc_comps:
                    has_any = True
                    best = max(doc_comps, key=lambda x: x[0].similarity)
                    plag_data.append([
                        doc_item.filename,
                        best[1],
                        f"{best[0].similarity:.1%}",
                    ])
                else:
                    plag_data.append([doc_item.filename, "No matches", "N/A"])

            if has_any:
                plag_table = Table(plag_data)
                plag_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#db2777')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fdf2f8')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(plag_table)

        doc.build(story)
        return buffer.getvalue()
