"""assessments.py - Assessment/session API routes. Every route is scoped to the logged-in account."""

from flask import Blueprint, jsonify, request, g

from db import get_connection
from analysis.assessment import build_summary, load_rows


assessments_bp = Blueprint("assessments", __name__)


def _session_owned_by_account(conn, sid, account_id):
    row = conn.execute(
        "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.id = ? AND u.account_id = ?",
        (sid, account_id),
    ).fetchone()
    return row is not None


@assessments_bp.route("/api/assessments", methods=["POST"])
def create_assessment():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    age = data.get("age")
    gender = str(data.get("gender", "")).strip()
    device = str(data.get("device", "mouse")).strip() or "mouse"

    if not name:
        return jsonify({"error": "Name is required."}), 400
    if age is None:
        return jsonify({"error": "Age is required."}), 400
    try:
        age = int(age)
    except (TypeError, ValueError):
        return jsonify({"error": "Age must be a number."}), 400
    if age <= 0 or age > 120:
        return jsonify({"error": "Invalid age."}), 400
    if not gender:
        return jsonify({"error": "Gender is required."}), 400

    with get_connection() as conn:
        user = conn.execute(
            "INSERT INTO users (account_id, name, age, gender) VALUES (?, ?, ?, ?)",
            (g.account_id, name, age, gender),
        )
        user_id = user.lastrowid

        session = conn.execute(
            "INSERT INTO sessions (user_id, device) VALUES (?, ?)",
            (user_id, device),
        )
        session_id = session.lastrowid

    return jsonify({"session_id": session_id}), 201


@assessments_bp.route("/api/assessments", methods=["GET"])
def list_assessments():
    with get_connection() as conn:
        sessions = conn.execute(
            """
            SELECT
                s.id AS session_id, s.created_at, s.completed_at, s.verdict_code,
                u.name, u.age, u.gender, s.device
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE u.account_id = ?
            ORDER BY s.created_at DESC
            """,
            (g.account_id,),
        ).fetchall()

        results = []
        for session in sessions:
            verdict_code = session["verdict_code"]
            if verdict_code in ("no_indicators", "retest", "see_doctor"):
                verdict = {
                    "code": verdict_code,
                    "title": {
                        "no_indicators": "No significant indicators detected",
                        "retest": "Inconclusive - please repeat the screening",
                        "see_doctor": "Possible indicators - please see a doctor",
                    }[verdict_code],
                }
            else:
                verdict = {"code": None, "title": "In progress"}

            results.append({
                "session_id": session["session_id"],
                "name": session["name"],
                "age": session["age"],
                "gender": session["gender"],
                "device": session["device"],
                "created_at": session["created_at"],
                "completed_at": session["completed_at"],
                "verdict_code": verdict["code"],
                "verdict_title": verdict["title"],
            })

    return jsonify(results)


@assessments_bp.route("/api/assessments/<int:sid>/finalize", methods=["POST"])
def finalize_assessment(sid):
    with get_connection() as conn:
        if not _session_owned_by_account(conn, sid, g.account_id):
            return jsonify({"error": "Assessment session not found."}), 404

        voice, move = load_rows(conn, sid)
        missing = [step for step in range(1, 9) if step not in voice and step not in move]
        if missing:
            return jsonify({"error": "Assessment is incomplete.", "missing_steps": missing}), 400

        from analysis.assessment import refresh_changes
        refresh_changes(conn, sid)

        summary = build_summary(conn, sid)
        if not summary:
            return jsonify({"error": "Could not build assessment summary."}), 500

        verdict_code = summary["verdict"]["code"]
        conn.execute(
            "UPDATE sessions SET completed_at = datetime('now'), verdict_code = ? WHERE id = ?",
            (verdict_code, sid),
        )
        summary = build_summary(conn, sid)

    return jsonify(summary)


@assessments_bp.route("/api/assessments/<int:sid>", methods=["GET"])
def get_assessment(sid):
    with get_connection() as conn:
        if not _session_owned_by_account(conn, sid, g.account_id):
            return jsonify({"error": "Assessment session not found."}), 404
        summary = build_summary(conn, sid)
        if not summary:
            return jsonify({"error": "Assessment session not found."}), 404

    return jsonify(summary)