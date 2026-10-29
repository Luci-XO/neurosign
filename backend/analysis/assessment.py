"""assessment.py - database helpers that tie the 8 steps together (change indices + summary)."""
import gzip
import json

import numpy as np

from analysis.movement_features import extract_movement_features
from analysis.scoring import (
    voice_change_index, movement_change_index, movement_stage_score, make_verdict,
)

VOICE_STEPS = (1, 2, 3, 4)
MOVE_STEPS = (5, 6, 7, 8)
BASE_STEP_FOR_TASK = {"spiral": 5, "wave": 6, "free": 7}
TASK_FOR_STEP = {5: "spiral", 6: "wave", 7: "free"}

STEP_NAMES = {
    1: "Voice - baseline 1", 2: "Voice - baseline 2", 3: "Voice - baseline 3", 4: "Voice - detection",
    5: "Spiral - baseline", 6: "Wave - baseline", 7: "Free shape - baseline", 8: "Repeat shape - detection",
}
STEP_ROLE = {1: "Baseline", 2: "Baseline", 3: "Baseline", 4: "Detection",
             5: "Baseline", 6: "Baseline", 7: "Baseline", 8: "Detection"}


def load_rows(conn, sid):
    voice = {r["step"]: r for r in conn.execute("SELECT * FROM voice_results WHERE session_id=?", (sid,)).fetchall()}
    move = {r["step"]: r for r in conn.execute("SELECT * FROM movement_results WHERE session_id=?", (sid,)).fetchall()}
    return voice, move


def refresh_changes(conn, sid):
    """Recompute change indices for step 4 and step 8 from the CURRENT baselines (safe after redos)."""
    voice, move = load_rows(conn, sid)
    if 4 in voice and all(s in voice for s in (1, 2, 3)):
        idx = voice_change_index(voice[4], [voice[1], voice[2], voice[3]])
        conn.execute("UPDATE voice_results SET change_index=? WHERE id=?", (idx, voice[4]["id"]))
    if 8 in move:
        base_step = BASE_STEP_FOR_TASK[move[8]["task_type"]]
        if base_step in move:
            idx = movement_change_index(move[8], move[base_step])
            conn.execute("UPDATE movement_results SET change_index=?, compared_step=? WHERE id=?",
                         (idx, base_step, move[8]["id"]))


def _refresh_saved_guide_scores(conn, sid, move):
    """Re-score older guided traces that predate the dedicated guide_deviation field."""
    for step, row in move.items():
        if step not in MOVE_STEPS or row["task_type"] not in ("spiral", "wave"):
            continue
        if row["guide_deviation"] is not None:
            continue
        raw = conn.execute(
            """SELECT r.data_gz FROM raw_signals r
               JOIN movement_results m ON m.id = r.movement_result_id
               WHERE m.session_id = ? AND m.step = ?""",
            (sid, step),
        ).fetchone()
        if raw is None:
            continue
        samples = json.loads(gzip.decompress(raw["data_gz"]).decode("utf-8"))
        features = extract_movement_features(samples, row["task_type"])
        conn.execute(
            "UPDATE movement_results SET guide_deviation=?, stage_score=? WHERE id=?",
            (features["guide_deviation"], movement_stage_score(features), row["id"]),
        )


def build_summary(conn, sid):
    s = conn.execute(
        """SELECT s.id, s.device, s.created_at, s.completed_at, s.verdict_code, u.name, u.age, u.gender
           FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id=?""", (sid,)).fetchone()
    if not s:
        return None
    voice, move = load_rows(conn, sid)
    _refresh_saved_guide_scores(conn, sid, move)
    _, move = load_rows(conn, sid)
    stages = []
    for step in range(1, 9):
        row = voice.get(step) or move.get(step)
        if not row:
            continue
        stages.append({
            "step": step, "name": STEP_NAMES[step], "role": STEP_ROLE[step],
            "kind": "voice" if step in VOICE_STEPS else "movement",
            "score": row["stage_score"], "change_index": row["change_index"], "data": row,
        })
    v_scores = [voice[k]["stage_score"] for k in VOICE_STEPS if k in voice and voice[k]["stage_score"] is not None]
    m_scores = [move[k]["stage_score"] for k in MOVE_STEPS if k in move and move[k]["stage_score"] is not None]
    # One clearly poor movement task should remain visible instead of being averaged down.
    verdict = make_verdict(
        float(np.mean(v_scores)) if v_scores else None,
        voice[4]["change_index"] if 4 in voice else None,
        float(max(m_scores)) if m_scores else None,
        move[8]["change_index"] if 8 in move else None,
    )
    for f in verdict["flags"]:
        if f["value"] is not None:
            f["value"] = round(f["value"], 1)
    return {"session": s, "stages": stages, "verdict": verdict}