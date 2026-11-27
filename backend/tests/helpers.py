import io
import random


def make_pdf(text: str, pages: int = 1, encrypt: str | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, encrypt=encrypt)
    for _ in range(pages):
        y = 800
        words = text.split()
        line = []
        for w in words:
            line.append(w)
            if len(" ".join(line)) > 80:
                c.drawString(40, y, " ".join(line))
                y -= 14
                line = []
        if line:
            c.drawString(40, y, " ".join(line))
        c.showPage()
    c.save()
    return buf.getvalue()


def make_image_pdf(text: str) -> bytes:
    """A 'scanned' PDF: text rendered into an image, no text layer."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1700, 600), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        font = ImageFont.load_default(size=40)
    draw.multiline_text((50, 50), text, fill="black", font=font, spacing=12)
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=150)
    return buf.getvalue()


def make_docx(paragraphs, table_rows=None) -> bytes:
    import docx

    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    if table_rows:
        t = d.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


VOCAB = (
    "river mountain policy energy student theory market culture system language history network "
    "garden science method signal ocean village engine budget harvest model record silver window "
    "travel border season letter museum doctor factory island vessel rhythm canvas planet"
).split()


def essay(seed: int, words: int = 300) -> str:
    rnd = random.Random(seed)
    out = []
    for i in range(words):
        w = rnd.choice(VOCAB)
        out.append(w.capitalize() if i % 12 == 0 else w)
        if i % 12 == 11:
            out[-1] += "."
    return " ".join(out) + "."
