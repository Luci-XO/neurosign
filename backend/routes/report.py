"""routes/report.py - GET /api/assessments/<id>/report.pdf : the single final PDF report."""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from flask import Blueprint, send_file, jsonify, g
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak, Image

from db import get_connection
from analysis.assessment import build_summary

report_bp = Blueprint("report", __name__)
GENDER_TEXT = {"male": "Male", "female": "Female", "other": "Other", "prefer_not_to_say": "Prefer not to say"}
EXERCISE_IMAGE_DIR = Path(__file__).resolve().parents[2] / "renderer" / "img" / "exercises"

EXERCISES = [
    {
        "title": "Seated marching",
        "description": "Sit toward the front of a stable chair with both feet on the floor. Sit tall, then slowly lift one foot a few inches, lower it, and alternate at an easy pace. Keep your back supported if needed.",
        "image": "seated-march.png",
        "cue": "Make the lift smaller or stop if it feels uncomfortable.",
    },
    {
        "title": "Supported heel raises",
        "description": "Stand facing a sturdy counter or heavy chair, holding it with both hands. Keeping your body upright, slowly lift your heels, then lower them with control.",
        "image": "heel-raises.png",
        "cue": "Stay close to your support; skip this if standing does not feel steady.",
    },
    {
        "title": "Seated knee extension",
        "description": "Sit in a stable chair with feet flat. Slowly straighten one knee within a comfortable range, pause briefly, then lower your foot and switch sides.",
        "image": "knee-extension.png",
        "cue": "Move slowly and do not lock your knee.",
    },
    {
        "title": "Supported side steps",
        "description": "Stand beside a clear, sturdy counter with one or both hands in contact with it. Take one small step sideways, bring the other foot in, and repeat for a few steps. Turn carefully.",
        "image": "supported-side-steps.png",
        "cue": "Keep steps small and avoid crossing your feet. Have someone nearby if balance is a concern.",
    },
    {
        "title": "Gentle shoulder rolls",
        "description": "Sit or stand comfortably with arms relaxed. Slowly lift your shoulders, roll them gently backward, and let them settle. Repeat a few times; reverse direction only if comfortable.",
        "image": "shoulder-rolls.png",
        "cue": "Keep your neck relaxed and use a small range.",
    },
    {
        "title": "Relaxed voice practice",
        "description": "Sit comfortably and take an easy breath. Read a short sentence or talk about something familiar at your usual pace and comfortable volume. Pause to breathe as needed.",
        "image": "relaxed-voice.png",
        "cue": "Do not force your volume or continue if your throat feels strained.",
    },
]


def _n(v, d=2, suffix=""):
    return "N/A" if v is None else f"{v:.{d}f}{suffix}"


def _score_color(v):
    if v is None:
        return colors.HexColor("#a9b7cc")
    return colors.HexColor("#1e8449" if v < 35 else "#d68910" if v < 50 else "#c0392b")


def _exercise_cards(styles):
    title_style = ParagraphStyle("exercise_title", parent=styles["Heading4"], fontSize=10,
                                 leading=12, textColor=colors.HexColor("#1a3a5c"), spaceAfter=3)
    body_style = ParagraphStyle("exercise_body", parent=styles["Normal"], fontSize=8.2, leading=10.5)
    cue_style = ParagraphStyle("exercise_cue", parent=body_style, textColor=colors.HexColor("#61708a"),
                               spaceBefore=3)
    cards = []
    for exercise in EXERCISES:
        card = Table([
            [Image(str(EXERCISE_IMAGE_DIR / exercise["image"]), width=3.12 * inch, height=2.53 * inch)],
            [Paragraph(escape(exercise["title"]), title_style)],
            [Paragraph(escape(exercise["description"]), body_style)],
            [Paragraph(f"<b>Tip:</b> {escape(exercise['cue'])}", cue_style)],
        ], colWidths=[3.12 * inch])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        cards.append(card)

    rows = [[cards[i], cards[i + 1]] for i in range(0, len(cards), 2)]
    grid = Table(rows, colWidths=[3.28 * inch, 3.28 * inch], hAlign="LEFT")
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return grid


@report_bp.route("/api/assessments/<int:sid>/report.pdf", methods=["GET"])
def report(sid):
    with get_connection() as conn:
        owned = conn.execute(
            "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.id = ? AND u.account_id = ?",
            (sid, g.account_id),
        ).fetchone()
        if not owned:
            return jsonify({"error": f"No assessment with id {sid}."}), 404
        summary = build_summary(conn, sid)
    if summary is None:
        return jsonify({"error": f"No assessment with id {sid}."}), 404
    if not summary["session"]["completed_at"]:
        return jsonify({"error": "Finish all 8 steps before creating the report."}), 409

    s, stages, v = summary["session"], summary["stages"], summary["verdict"]
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, leading=10)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=13)
    vcolor = colors.HexColor(v["color"])
    el = [Paragraph("NeuroSign Screening Report", ss["Title"]),
          Paragraph("Research / screening demo. This report is NOT a medical diagnosis and does not replace "
                    "examination by a qualified doctor. All processing was done locally on this computer.",
                    ParagraphStyle("w", parent=small, textColor=colors.HexColor("#a33"), spaceAfter=10))]

    info = Table([
        ["Name", escape(s["name"]), "Date (UTC)", s["created_at"]],
        ["Age", str(s["age"]), "Input device", s["device"].capitalize()],
        ["Gender", GENDER_TEXT.get(s["gender"], s["gender"]), "Assessment ID", str(s["id"])],
    ], colWidths=[0.9 * inch, 2.3 * inch, 1.1 * inch, 2.3 * inch])
    info.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                              ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
    el += [info, Spacer(1, 12)]

    box = Table([[Paragraph("FINAL SCREENING RESULT", ParagraphStyle("k", parent=small, textColor=colors.white))],
                [Paragraph(escape(v["title"]), ParagraphStyle("t", parent=ss["Heading2"], textColor=colors.white, spaceAfter=2))],
                [Paragraph(escape(v["message"]), ParagraphStyle("m", parent=body, textColor=colors.white))]],
               colWidths=[6.6 * inch])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), vcolor), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    el += [box, Spacer(1, 10), Paragraph("What was checked", ss["Heading3"])]

    flag_rows = [["Check", "Value", "Flag at", "Result"]]
    for f in v["flags"]:
        flag_rows.append([Paragraph(escape(f["label"]), small), _n(f["value"], 1), f">= {f['threshold']:.0f}",
                          "FLAGGED" if f["flagged"] else ("not available" if f["value"] is None else "ok")])
    ft = Table(flag_rows, colWidths=[3.8 * inch, 0.8 * inch, 0.8 * inch, 1.2 * inch])
    ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    for i, f in enumerate(v["flags"], 1):
        if f["flagged"]:
            ft.setStyle(TableStyle([("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#c0392b")), ("FONTNAME", (3, i), (3, i), "Helvetica-Bold")]))
    el += [ft, Spacer(1, 6),
           Paragraph(f"{v['flag_count']} of 4 checks flagged: 0 = no indicators, 1 = repeat the screening, 2 or more = see a doctor.", small),
           Spacer(1, 12)]

    rows = [["Step", "Test", "Role", "Stage score", "Change", "Key measurements"]]
    for st in stages:
        d = st["data"]
        if st["kind"] == "voice":
            key = (f"F0 {_n(d['f0_mean'], 0)} Hz; jitter {_n(d['jitter_local'] * 100, 2)}%; "
                   f"shimmer {_n(d['shimmer_local'] * 100, 2)}%; HNR {_n(d['hnr'], 1)} dB")
        else:
            key = (f"{_n(d['duration_s'], 1)} s; tremor share {_n((d['tremor_share'] or 0) * 100, 0)}%; "
                   f"guide distance {_n(d.get('guide_deviation'), 1)} px; "
                   f"peak {_n(d['peak_freq_hz'], 1)} Hz; vel. CV {_n(d['velocity_cv'], 2)}")
        rows.append([str(st["step"]), Paragraph(st["name"], small), st["role"], _n(st["score"], 1),
                     _n(st["change_index"], 1) if st["role"] == "Detection" else "-", Paragraph(escape(key), small)])
    t = Table(rows, colWidths=[0.4 * inch, 1.5 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch, 2.2 * inch], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f7")])]))
    el += [KeepTogether([Paragraph("Score of every stage (0-100, lower = more regular)", ss["Heading3"]), t])]

    chart = Drawing(450,150)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 35, 25, 395, 105
    bc.data = [[(st["score"] or 0) for st in stages]]
    bc.categoryAxis.categoryNames = [f"Step {st['step']}" for st in stages]
    bc.categoryAxis.labels.fontSize = 7
    bc.valueAxis.valueMin, bc.valueAxis.valueMax, bc.valueAxis.valueStep = 0, 100, 25
    bc.valueAxis.labels.fontSize = 7
    for i, st in enumerate(stages):
        bc.bars[(0, i)].fillColor = _score_color(st["score"])
    chart.add(bc)
    el += [Spacer(1, 6), chart,
           Paragraph("How the scores are calculated", ss["Heading3"]),
           Paragraph("<b>Voice (steps 1-4):</b> a sustained 'aaah' is analysed with Praat. The stage score compares "
                     "local jitter and local shimmer with the reference thresholds in Praat's voice report "
                     "(1.04% and 3.81%, each equal to a score of 50). Steps 1-3 form your personal baseline; step 4 "
                     "is compared with the mean of those three recordings.", body), Spacer(1, 4),
           Paragraph("<b>Movement (steps 5-8):</b> on guided spiral and wave tasks, the trace is compared "
                     "with the guide at matching drawing progress. The 95th-percentile distance is used so "
                     "sustained off-guide tracing is not hidden by on-guide points. Distances within 10 px are "
                     "treated as tracing tolerance; 50 px maps to the maximum guide-deviation score. The movement "
                     "stage score is the higher of this provisional guide score and the tremor-band score. Free "
                     "drawing has no fixed guide. Guide distance is evaluated separately from step-8 baseline "
                     "change. Saved guided recordings are refreshed from their raw trace when results are opened. "
                     "These thresholds are "
                     "demo settings, not clinically validated.", body),
           Spacer(1, 4),
           Paragraph("<b>Change vs baseline:</b> average fold-worsening across measures, scaled so 2x = 33, 4x = 67 "
                     "and 8x or more = 100.", body),
           PageBreak(),
           Paragraph("Gentle exercise ideas", ss["Heading2"]),
           Paragraph("These are general activities for information only. They are not a treatment plan and are not "
                     "personalized from your screening score.", body),
           Spacer(1, 10),
           _exercise_cards(ss),
           Paragraph("<b>Safety:</b> Check with your doctor or physical therapist before starting, especially if you "
                     "have balance concerns. Use stable support for standing activities. Stop if you feel pain, become "
                     "dizzy, or are unusually short of breath. Move only within a comfortable range.", body),
    ]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title="NeuroSign Screening Report").build(el)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"neurosign_report_{sid}.pdf")