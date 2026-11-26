"""Build a print-ready PDF from the same report and images shown in Inspect."""

from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
import os

from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.platypus import Flowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ASSETS = Path(__file__).resolve().parent.parent / "frontend" / "assets"
NAVY = colors.HexColor("#071321")
CYAN = colors.HexColor("#35E7EE")
VIOLET = colors.HexColor("#5845E7")
INK = colors.HexColor("#142A42")
MUTED = colors.HexColor("#4F6276")
LINE = colors.HexColor("#DAE3ED")
PALE = colors.HexColor("#F4F8FC")
STATUS_COLORS = {
    "PASS": (colors.HexColor("#11623C"), colors.HexColor("#E7F6EE")),
    "FAIL": (colors.HexColor("#A12838"), colors.HexColor("#FBECEE")),
    "REVIEW": (colors.HexColor("#775003"), colors.HexColor("#FFF4DA")),
}
BUILD_LOCK = Lock()


def _fonts() -> tuple[str, str]:
    """Match the Windows browser font when its TrueType files are available."""
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    try:
        pdfmetrics.registerFont(TTFont("InspectionUI", str(fonts / "segoeui.ttf")))
        pdfmetrics.registerFont(TTFont("InspectionUI-Bold", str(fonts / "segoeuib.ttf")))
    except (OSError, TTFError):
        return "Helvetica", "Helvetica-Bold"
    return "InspectionUI", "InspectionUI-Bold"


FONT, FONT_BOLD = _fonts()
BODY = ParagraphStyle("ReportBody", fontName=FONT, fontSize=10, leading=15, textColor=INK)
LABEL = ParagraphStyle("ReportLabel", parent=BODY, fontName=FONT_BOLD, fontSize=9, leading=13, textColor=MUTED)
TITLE = ParagraphStyle("ReportTitle", parent=BODY, fontName=FONT_BOLD, fontSize=26, leading=32)
SECTION = ParagraphStyle("ReportSection", parent=BODY, fontName=FONT_BOLD, fontSize=15, leading=20, keepWithNext=True)


def _text(value: object, style: ParagraphStyle = BODY) -> Paragraph:
    """Treat names and report fields as text, including any XML-like characters."""
    return Paragraph(escape(str(value)), style)


def _table(data, widths, rules, *, repeat_rows=0):
    table_type = LongTable if repeat_rows else Table
    table = table_type(data, colWidths=widths, hAlign="LEFT", repeatRows=repeat_rows)
    table.setStyle(TableStyle(rules))
    return table


class _BoardPreview(Flowable):
    """Draw an uncropped PCB photo or a labeled placeholder inside a fixed card."""

    def __init__(self, width: float, title: str, path: Path | None):
        super().__init__()
        self.width = width
        self.height = 151
        self.title = title
        self.image = None
        if path is not None:
            try:
                with Image.open(path) as source:
                    photo = ImageOps.exif_transpose(source).convert("RGB")
                    photo.thumbnail((int(width * 3), int(self.height * 3)), Image.Resampling.LANCZOS)
                    self.image = ImageReader(photo)
            except OSError:
                self.image = None

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(PALE)
        canvas.setStrokeColor(LINE)
        canvas.roundRect(0, 0, self.width, self.height, 8, fill=1)
        canvas.setFont(FONT_BOLD, 10)
        canvas.setFillColor(INK)
        canvas.drawString(12, self.height - 17, self.title)
        if self.image is None:
            message = "Original image unavailable" if self.title == "Original PCB" else "Annotated image unavailable"
            canvas.setFont(FONT, 9)
            canvas.setFillColor(MUTED)
            canvas.drawCentredString(self.width / 2, 66, message)
            return

        width, height = self.image.getSize()
        scale = min((self.width - 18) / width, (self.height - 35) / height)
        width *= scale
        height *= scale
        canvas.drawImage(self.image, (self.width - width) / 2, 9 + (self.height - 35 - height) / 2, width, height)


def _branding(canvas, document) -> None:
    width, height = document.pagesize
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 74, width, 74, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, height - 76, width * .72, 2, fill=1, stroke=0)
    canvas.setFillColor(VIOLET)
    canvas.rect(width * .72, height - 76, width * .28, 2, fill=1, stroke=0)

    left = document.leftMargin + 6
    right = width - left
    logo = ASSETS / "brand-mark.png"
    if logo.is_file():
        canvas.drawImage(str(logo), left - 3, height - 58, width=42, height=42, mask="auto")
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, 18)
    canvas.drawString(left + 46, height - 43, "Circuit-Check-AI")
    canvas.setFillColor(LINE)
    canvas.setFont(FONT, 9)
    canvas.drawRightString(right, height - 42, "PCB inspection report")

    canvas.setStrokeColor(LINE)
    canvas.line(left, 35, right, 35)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT, 9)
    canvas.drawRightString(right, 21, f"Page {document.page}")
    canvas.restoreState()


def _summary(inspection: dict, width: float):
    status = inspection["status"]
    ink, tint = STATUS_COLORS[status]
    labels = ("Verdict", "Confirmed defects", "Review candidates")
    values = (status, inspection["total_defects"], inspection["total_review_candidates"])
    value_style = ParagraphStyle("SummaryValue", parent=BODY, fontName=FONT_BOLD, fontSize=18, leading=24)
    verdict_style = ParagraphStyle("VerdictValue", parent=value_style, textColor=ink)
    cells = [
        [_text(label, LABEL), _text(value, verdict_style if index == 0 else value_style)]
        for index, (label, value) in enumerate(zip(labels, values))
    ]
    return _table([cells], [width / 3] * 3, [
        ("BACKGROUND", (0, 0), (0, 0), tint),
        ("BACKGROUND", (1, 0), (-1, 0), PALE),
        ("BOX", (0, 0), (-1, -1), .7, LINE),
        ("LINEBEFORE", (1, 0), (-1, -1), .7, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ])


def _findings(report: dict, width: float):
    findings = [
        (finding, status)
        for key, status in (("defects", "Confirmed"), ("review_candidates", "Review"))
        for finding in report[key]
    ]
    if not findings:
        return _text("No confirmed defects or review candidates.")

    heading = ParagraphStyle("FindingsHeader", parent=LABEL, textColor=colors.white)
    header = [_text(label, heading) for label in ("No.", "Defect type", "Severity", "Confidence", "Status")]
    rows = [header]
    for number, (finding, status) in enumerate(findings, start=1):
        name = finding["class_name"].replace("_", " ").capitalize()
        rows.append([
            _text(number),
            _text(name),
            _text(finding["severity"].capitalize()),
            _text(f"{finding['confidence']:.2%}"),
            _text(status),
        ])

    return _table(rows, [38, width - 294, 83, 87, 86], [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 1), (-1, -1), .5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ], repeat_rows=1)


def build_inspection_pdf(
    inspection_id: str,
    report: dict,
    *,
    original_path: Path | None = None,
    annotated_path: Path | None = None,
) -> bytes:
    """Render a saved report and its matching images to a single in-memory PDF."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=96, bottomMargin=46,
        title="PCB inspection report | Circuit-Check-AI", author="Circuit-Check-AI",
    )
    # The default Platypus frame has six points of padding on each side.
    width = document.width - 12
    filename = report["source_image"].replace("\\", "/").rsplit("/", 1)[-1]
    timestamp = report["timestamp"].replace("T", " ", 1)
    gap = 12
    image_width = (width - gap) / 2
    previews = _table([[
        _BoardPreview(image_width, "Original PCB", original_path),
        "",
        _BoardPreview(image_width, "AI Inspection", annotated_path),
    ]], [image_width, gap, image_width], [
        (padding, (0, 0), (-1, -1), 0)
        for padding in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")
    ])
    metadata = _table([
        [_text("Inspection ID", LABEL), _text(inspection_id)],
        [_text("Inspected", LABEL), _text(timestamp)],
        [_text("File", LABEL), _text(filename)],
    ], [90, width - 90], [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    story = [
        _text("Inspection report", TITLE), Spacer(1, 7), metadata, Spacer(1, 15),
        _summary(report["inspection"], width), Spacer(1, 18), previews, Spacer(1, 17),
        _text("Findings", SECTION), Spacer(1, 6), _findings(report, width),
    ]
    # ReportLab shares registered TrueType font objects across builds.
    with BUILD_LOCK:
        document.build(story, onFirstPage=_branding, onLaterPages=_branding)
    return buffer.getvalue()
