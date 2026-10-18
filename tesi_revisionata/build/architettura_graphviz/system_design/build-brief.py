"""Compose six A4 pages from shared content and vector Graphviz figures."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


BASE = Path(__file__).resolve().parent
OUTPUT = BASE.parents[3] / 'output' / 'pdf' / 'architettura'
INK = colors.HexColor('#17343F')
ACCENT = colors.HexColor('#116F64')


def make_briefs() -> None:
    """Use the same source-specific graphs and example steps as the HTML."""
    pdfmetrics.registerFont(TTFont('MTBArial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('MTBArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
    body = ParagraphStyle('body', fontName='MTBArial', fontSize=9.5, leading=13, textColor=INK)
    lead = ParagraphStyle('lead', parent=body, fontSize=10, leading=14)
    labels = ParagraphStyle('labels', parent=body, fontName='MTBArialBold', textColor=ACCENT)
    content = json.loads((BASE / 'verifica' / 'brief-content.json').read_text(encoding='utf-8'))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    width, height = A4
    margin = 38
    available_width = width - 2 * margin

    def paragraph(text: str, style: ParagraphStyle) -> tuple[Paragraph, float]:
        item = Paragraph(escape(text).replace('\n', '<br/>'), style)
        _, used_height = item.wrap(available_width, height)
        return item, used_height

    for example, document in content.items():
        writer = PdfWriter()
        for number, page in enumerate(document['pages'], 1):
            buffer = BytesIO()
            sheet = canvas.Canvas(buffer, pagesize=A4)
            sheet.setTitle('Architettura per il relatore - versione breve')
            y = height - margin
            sheet.setFillColor(INK)
            sheet.setFont('MTBArialBold', 17)
            sheet.drawString(margin, y, f"{number}. {page['title']}")
            y -= 21
            sheet.setFont('MTBArial', 9)
            sheet.setFillColor(ACCENT)
            sheet.drawString(margin, y, document['label'] + ' · esempio BRAF')
            y -= 14
            intro, intro_height = paragraph(page['lead'], lead)
            intro.drawOn(sheet, margin, y - intro_height)
            y -= intro_height + 14

            clarification = page.get('clarification')
            if clarification:
                note, note_height = paragraph(clarification['brief'], body)
                note.drawOn(sheet, margin, y - note_height)
                y -= note_height + 10

            blocks = []
            example_height = 0.0
            for title, key in [('Da dove arriviamo', 'input'), ('Che cosa cambia', 'action'), ('Che cosa portiamo avanti', 'result')]:
                label, label_height = paragraph(title, labels)
                text, text_height = paragraph(page['step'][key], body)
                blocks.append((label, label_height, text, text_height))
                example_height += label_height + text_height + 9
            graph_top = y
            graph_height = min(325.0, graph_top - example_height - 83)
            if graph_height < 160:
                raise ValueError(f"Insufficient space in {example}/{page['title']}")
            graph = PdfReader(BASE / 'figure' / 'percorsi' / (page['key'] + '.pdf')).pages[0]
            scale = min(available_width / float(graph.mediabox.width), graph_height / float(graph.mediabox.height))
            graph_x = margin + (available_width - float(graph.mediabox.width) * scale) / 2
            graph_y = graph_top - graph_height + (graph_height - float(graph.mediabox.height) * scale) / 2
            y = graph_top - graph_height - 17
            sheet.setFillColor(ACCENT)
            sheet.setFont('MTBArialBold', 11)
            sheet.drawString(margin, y, 'Esempio trasversale · dati documentati')
            y -= 10
            for label, label_height, text, text_height in blocks:
                label.drawOn(sheet, margin, y - label_height)
                y -= label_height
                text.drawOn(sheet, margin, y - text_height)
                y -= text_height + 9
            if y < 43:
                raise ValueError(f"Example overflows in {example}/{page['title']}")
            sheet.setFont('MTBArial', 7.5)
            sheet.setFillColor(INK)
            sheet.drawString(margin, 26, 'Caso sintetico. Raccordi didattici; gli esiti dichiarati provengono dai dati documentati.')
            sheet.drawRightString(width - margin, 26, f'{number}/6')
            sheet.save()
            composed = PdfReader(BytesIO(buffer.getvalue())).pages[0]
            composed.merge_transformed_page(graph, Transformation().scale(scale).translate(graph_x, graph_y))
            writer.add_page(composed)
        writer.write(OUTPUT / f'Relatore_breve_{example}.pdf')
        print(f'Versione breve {example}: sei pagine A4 vettoriali.')


if __name__ == '__main__':
    make_briefs()
