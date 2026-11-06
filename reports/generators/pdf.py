"""
Minimal PDF report generator using ReportLab.
Produces a single-page summary report for a given date range.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


def build_summary_pdf(title: str, rows: list[tuple], narrative: str = '') -> bytes:
    """
    Build a simple tabular PDF report.

    Args:
        title: Report title string.
        rows: List of (label, value) tuples for the summary table.
        narrative: Optional text block appended below the table.

    Returns:
        PDF file content as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles['Title']))
    story.append(Spacer(1, 0.5 * cm))

    if rows:
        table_data = [['Indicator', 'Value']] + list(rows)
        table = Table(table_data, colWidths=[10 * cm, 6 * cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.5 * cm))

    if narrative:
        story.append(Paragraph('Narrative Summary', styles['Heading2']))
        for para in narrative.split('\n\n'):
            if para.strip():
                story.append(Paragraph(para.strip(), styles['BodyText']))
                story.append(Spacer(1, 0.3 * cm))

    doc.build(story)
    return buffer.getvalue()
