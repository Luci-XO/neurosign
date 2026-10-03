"""routes/steps.py - analyse one voice step (1-4) or one movement step (5-8). Redoing a step replaces it."""
import gzip
import json
import os
import tempfile

from flask import Blueprint, request, jsonify

import config
from db import get_connection
from analysis.voice_features import extract_voice_features, VoiceAnalysisError
from analysis.movement_features import extract_movement_features, MovementAnalysisError
from analysis.scoring import voice_stage_score, movement_stage_score
from analysis.assessment import (
    VOICE_STEPS, MOVE_STEPS, TASK_FOR_STEP, BASE_STEP_FOR_TASK, load_rows, refresh_changes,
)

steps_bp = Blueprint("steps", __name__)

# Order must match ml/train_voice_rf.py
MODEL_FEATURES = [
    "jitter_local", "jitter_rap", "jitter_ppq5", "jitter_ddp",
    "shimmer_local", "shimmer_db", "shimmer_apq3", "shimmer_apq5", "shimmer_dda", "hnr",
]
_model = None


def _model_probability(features):
    """Reference value only (not used in the verdict). None if no trained model exists."""
    global _model
    if _model is None and config.VOICE_MODEL_PATH.exists():
        import joblib
        _model = joblib.load(config.VOICE_MODEL_PATH)
    if _model is None:
        return None
    return round(float(_model.predict_proba([[features[f] for f in MODEL_FEATURES]])[0][1]), 4)


def _insert(conn, table, row):
    cols = ", ".join(row)
    marks = ", ".join(["?"] * len(row))
    return conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values())).lastrowid


@steps_bp.route("/api/assessments/<int:sid>/voice", methods=["POST"])
def voice_step(sid):
    step = request.form.get("step", type=int)
    if step not in VOICE_STEPS:
        return jsonify({"error": "Voice 'step' must be 1-4."}), 400
    if "audio" not in request.files:
        return jsonify({"error": "No 'audio' file in the request."}), 400

    with get_connection() as conn:
        if not conn.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": f"No assessment with id {sid}."}), 404
        voice, _ = load_rows(conn, sid)
    if step == 4 and not all(s in voice for s in (1, 2, 3)):
        return jsonify({"error": "Finish the three baseline voice steps first."}), 409

    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        request.files["audio"].save(tmp)
        try:
            features = extract_voice_features(tmp)
        except VoiceAnalysisError as e:
            return jsonify({"error": str(e)}), 422
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    row = {"session_id": sid, "step": step, **features,
           "model_probability": _model_probability(features),
           "stage_score": voice_stage_score(features)}
    with get_connection() as conn:
        conn.execute("DELETE FROM voice_results WHERE session_id=? AND step=?", (sid, step))
        _insert(conn, "voice_results", row)
        refresh_changes(conn, sid)
        saved = conn.execute("SELECT stage_score, change_index, model_probability FROM voice_results "
                             "WHERE session_id=? AND step=?", (sid, step)).fetchone()
    return jsonify({"step": step, "features": features, **saved}), 201


@steps_bp.route("/api/assessments/<int:sid>/movement", methods=["POST"])
def movement_step(sid):
    d = request.get_json(silent=True) or {}
    step, samples = d.get("step"), d.get("samples")
    if step not in MOVE_STEPS:
        return jsonify({"error": "Movement 'step' must be 5-8."}), 400
    task = TASK_FOR_STEP.get(step) or d.get("task_type")
    if task not in BASE_STEP_FOR_TASK:
        return jsonify({"error": "task_type must be 'spiral', 'wave' or 'free'."}), 400
    if not isinstance(samples, list) or not samples:
        return jsonify({"error": "Field 'samples' must be a non-empty list."}), 400

    with get_connection() as conn:
        if not conn.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": f"No assessment with id {sid}."}), 404
        _, move = load_rows(conn, sid)
    if step == 8 and BASE_STEP_FOR_TASK[task] not in move:
        return jsonify({"error": f"Finish step {BASE_STEP_FOR_TASK[task]} first (that shape is your baseline)."}), 409

    try:
        features = extract_movement_features(samples, task)
    except MovementAnalysisError as e:
        return jsonify({"error": str(e)}), 422

    row = {"session_id": sid, "step": step, **features, "stage_score": movement_stage_score(features)}
    with get_connection() as conn:
        conn.execute("DELETE FROM movement_results WHERE session_id=? AND step=?", (sid, step))  # cascades raw_signals
        rid = _insert(conn, "movement_results", row)
        conn.execute("INSERT INTO raw_signals (movement_result_id, data_gz) VALUES (?,?)",
                     (rid, gzip.compress(json.dumps(samples).encode("utf-8"))))
        refresh_changes(conn, sid)
        saved = conn.execute("SELECT stage_score, change_index, compared_step FROM movement_results "
                             "WHERE session_id=? AND step=?", (sid, step)).fetchone()
    return jsonify({"step": step, "features": features, **saved}), 201