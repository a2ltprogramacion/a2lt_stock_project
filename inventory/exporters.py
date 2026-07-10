"""
inventory/exporters.py
======================
Exportadores a CSV y PDF para los reportes de Fase 4.

CSV: stdlib `csv` (encoding utf-8-sig para Excel en español).
PDF: reportlab (sin WeasyPrint) — A4 landscape, tabular simple.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.http import HttpResponse


# ─────────────────────────────────────────────────────────────────────────────
# CSV
# ─────────────────────────────────────────────────────────────────────────────

def export_csv(resultado: dict, filename: str = 'reporte.csv') -> HttpResponse:
    """
    Convierte el resultado de un reporte (formato reports.*)
    en una HttpResponse con CSV listo para descargar.
    """
    columns = resultado.get('columns', [])
    rows = resultado.get('rows', [])
    totals = resultado.get('totals', {})
    meta = resultado.get('meta', {})

    buffer = io.StringIO()
    # utf-8-sig -> BOM para que Excel detecte Unicode automáticamente
    buffer.write('\ufeff')
    writer = csv.writer(buffer)

    # Meta header (opcional pero informativo)
    if meta:
        writer.writerow([f"{k}: {v}" for k, v in meta.items()])
        writer.writerow([])

    # Header
    writer.writerow([label for _, label in columns])

    # Rows
    for row in rows:
        writer.writerow([row.get(key, '') for key, _ in columns])

    # Totales
    if totals:
        writer.writerow([])
        writer.writerow(['TOTALES'] + [''] * (len(columns) - 1))
        for k, v in totals.items():
            writer.writerow([f'  {k}', v])

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# PDF (reportlab)
# ─────────────────────────────────────────────────────────────────────────────

def export_pdf(resultado: dict, filename: str = 'reporte.pdf') -> HttpResponse:
    """
    Convierte el resultado de un reporte en un PDF landscape A4
    con tabla simple + bloque de totales al pie.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )
    from reportlab.lib.enums import TA_LEFT

    columns = resultado.get('columns', [])
    rows = resultado.get('rows', [])
    totals = resultado.get('totals', {})
    meta = resultado.get('meta', {})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=meta.get('titulo', 'Reporte'),
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'Title2', parent=styles['Title'], fontSize=14, spaceAfter=6
    )
    style_meta = ParagraphStyle(
        'Meta', parent=styles['Normal'], fontSize=8, textColor=colors.grey,
        spaceAfter=10
    )
    elements = []

    # Titulo
    elements.append(Paragraph(
        meta.get('titulo', 'Reporte'), style_title
    ))
    # Meta
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if k not in ('titulo', 'empresa_id')]
    if meta_lines:
        elements.append(Paragraph(' · '.join(meta_lines), style_meta))

    # Tabla
    header = [label for _, label in columns]
    data = [header]
    for row in rows:
        data.append([str(row.get(key, '')) for key, _ in columns])

    # Ancho columnas aproximado: repartir el ancho util
    page_width = landscape(A4)[0] - 30 * mm
    n_cols = len(columns) or 1
    col_width = page_width / n_cols
    table = Table(data, colWidths=[col_width] * n_cols, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    # Totales
    if totals:
        tot_data = [['TOTALES', '']] + [
            [f"  {k}", str(v)] for k, v in totals.items()
        ]
        tbl_t = Table(tot_data, colWidths=[page_width * 0.5, page_width * 0.5])
        tbl_t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ede9fe')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#faf5ff')),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.HexColor('#a78bfa')),
        ]))
        elements.append(tbl_t)

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
