"""routes/report.py - GET /api/assessments/<id>/report.pdf : the single final PDF report."""
import io
from xml.sax.saxutils import escape

from flask import Blueprint, send_file, jsonify
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from db import get_connection
from analysis.assessment import build_summary

report_bp = Blueprint("report", __name__)
GENDER_TEXT = {"male": "Male", "female": "Female", "other": "Other", "prefer_not_to_say": "Prefer not to say"}


def _n(v, d=2, suffix=""):
    return "N/A" if v is None else f"{v:.{d}f}{suffix}"


def _score_color(v):
    if v is None:
        return colors.HexColor("#a9b7cc")
    return colors.HexColor("#1e8449" if v < 35 else "#d68910" if v < 50 else "#c0392b")


@report_bp.route("/api/assessments/<int:sid>/report.pdf", methods=["GET"])
def report(sid):
    with get_connection() as conn:
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

    # ---- score per stage
    rows = [["Step", "Test", "Role", "Stage score", "Change", "Key measurements"]]
    for st in stages:
        d = st["data"]
        if st["kind"] == "voice":
            key = (f"F0 {_n(d['f0_mean'], 0)} Hz; jitter {_n(d['jitter_local'] * 100, 2)}%; "
                   f"shimmer {_n(d['shimmer_local'] * 100, 2)}%; HNR {_n(d['hnr'], 1)} dB")
        else:
            key = (f"{_n(d['duration_s'], 1)} s; tremor share {_n((d['tremor_share'] or 0) * 100, 0)}%; "
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
    el += [Spacer(1, 6), chart]
    el += [Paragraph("How the scores are calculated", ss["Heading3"]),
           Paragraph("<b>Voice (steps 1-4):</b> a sustained 'aaah' is analysed with Praat. The stage score compares "
                     "local jitter and local shimmer with the reference thresholds in Praat's voice report "
                     "(1.04% and 3.81%, each equal to a score of 50). Steps 1-3 form your personal baseline; step 4 "
                     "is compared with the mean of those three recordings.", body), Spacer(1, 4),
           Paragraph("<b>Movement (steps 5-8):</b> the traced path is resampled to 100 Hz, the slow intentional motion "
                     "is removed with a 2 Hz high-pass filter, and the share of remaining 3-12 Hz energy that lies in "
                     "the 4-6 Hz rest-tremor band gives the stage score. Step 8 repeats one earlier shape and is "
                     "compared with that shape's baseline (velocity variability, jerk, path deviation, tremor power).", body),
           Spacer(1, 4),
           Paragraph("<b>Change vs baseline:</b> average fold-worsening across measures, scaled so 2x = 33, 4x = 67 "
                     "and 8x or more = 100.", body)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title="NeuroSign Screening Report").build(el)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"neurosign_report_{sid}.pdf")