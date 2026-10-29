"""
scoring.py - pure scoring functions (no database). SCREENING DEMO ONLY - NOT A DIAGNOSIS.

Two kinds of numbers:
  stage score (0-100)  : absolute irregularity of ONE recording against provisional reference values.
                         Voice  : jitter/shimmer vs Praat's published voice-report thresholds
                                  (jitter 1.04 %, shimmer 3.81 % -> each maps to 50).
                         Movement: maximum of tremor-band and guided-path-deviation scores
                                  (PROVISIONAL scales, not clinically calibrated - tune below).
  change index (0-100) : how much the detection test (step 4 / step 8) moved away from the person's
                         OWN baseline, as a fold change (2x worse = 33, 4x = 67, 8x or more = 100).
"""
import math

import numpy as np

# ---- tunable constants (all in one place) -------------------------------------------------
JITTER_REF = 0.0104          # fraction (1.04 %)
SHIMMER_REF = 0.0381         # fraction (3.81 %)
TREMOR_SHARE_FLOOR = 0.22    # ~ share of a flat spectrum (2 Hz of 9 Hz) -> score 0
TREMOR_SHARE_CEIL = 0.60     # -> score 100
GUIDE_DEVIATION_TOLERANCE_PX = 10.0  # nearest-guide p90 within this is treated as tracing tolerance
GUIDE_DEVIATION_CEIL_PX = 50.0       # -> guide-deviation score 100
FLAG_LEVEL = 50.0            # stage-score level at which a signal is flagged
FLAG_CHANGE = 35.0           # change-index level at which a signal is flagged

VOICE_CHANGE_METRICS = {     # +1 = higher is worse, -1 = lower is worse
    "jitter_local": 1, "jitter_rap": 1, "jitter_ppq5": 1, "jitter_ddp": 1,
    "shimmer_local": 1, "shimmer_db": 1, "shimmer_apq3": 1, "shimmer_apq5": 1, "shimmer_dda": 1,
    "hnr": -1,
}
MOVEMENT_CHANGE_METRICS = {
    "tremor_power_4_6": 1, "velocity_cv": 1, "jerk_rms": 1,
}

VERDICTS = {
    "no_indicators": {
        "title": "No significant indicators detected",
        "color": "#1e8449",
        "message": ("In this session your voice and movement measurements stayed within the screening "
                    "thresholds. This does not rule out Parkinson's disease or any other condition. If you "
                    "notice tremor, slowness, stiffness, balance problems or voice changes, see a doctor "
                    "regardless of this result."),
    },
    "retest": {
        "title": "Inconclusive - please repeat the screening",
        "color": "#d68910",
        "message": ("One measure crossed its threshold. This is often caused by background noise, tiredness, "
                    "a different input device or a poor recording. Repeat the screening in a quiet room on "
                    "another day with the same device. If the result persists, or you have symptoms, consult "
                    "a doctor."),
    },
    "see_doctor": {
        "title": "Possible indicators - please see a doctor",
        "color": "#c0392b",
        "message": ("Two or more measures crossed their thresholds. This is NOT a diagnosis and does not mean "
                    "you have Parkinson's disease, but it is a good reason to have a doctor or neurologist "
                    "examine you. Take this report with you."),
    },
}


def _clip(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def voice_stage_score(f):
    jitter = _clip(f["jitter_local"] / JITTER_REF * 50.0)
    shimmer = _clip(f["shimmer_local"] / SHIMMER_REF * 50.0)
    return round((jitter + shimmer) / 2.0, 1)


def movement_stage_score(f):
    share = f.get("tremor_share") or 0.0
    span = TREMOR_SHARE_CEIL - TREMOR_SHARE_FLOOR
    tremor_score = _clip((share - TREMOR_SHARE_FLOOR) / span * 100.0)

    deviation = f.get("guide_deviation")
    if deviation is None:
        return round(tremor_score, 1)
    guide_score = _clip(
        (deviation - GUIDE_DEVIATION_TOLERANCE_PX)
        / (GUIDE_DEVIATION_CEIL_PX - GUIDE_DEVIATION_TOLERANCE_PX)
        * 100.0
    )
    return round(max(tremor_score, guide_score), 1)


def _fold_change_index(pairs):
    """pairs: (new, baseline, direction). Mean of clipped log2 fold-worsening, scaled to 0-100."""
    vals = []
    for new, base, direction in pairs:
        if new is None or base is None or new <= 0 or base <= 0:
            continue
        ratio = new / base if direction > 0 else base / new
        vals.append(_clip(math.log2(ratio), 0.0, 3.0))
    return round(float(np.mean(vals)) / 3.0 * 100.0, 1) if vals else None


def voice_change_index(detect_row, baseline_rows):
    pairs = []
    for metric, direction in VOICE_CHANGE_METRICS.items():
        base_vals = [r[metric] for r in baseline_rows if r.get(metric) is not None]
        if base_vals:
            pairs.append((detect_row.get(metric), float(np.mean(base_vals)), direction))
    return _fold_change_index(pairs)


def movement_change_index(detect_row, baseline_row):
    pairs = [(detect_row.get(m), baseline_row.get(m), d) for m, d in MOVEMENT_CHANGE_METRICS.items()]
    return _fold_change_index(pairs)


def make_verdict(voice_level, voice_change, move_level, move_change):
    checks = [
        ("voice_level", "Voice irregularity level, steps 1-4 (jitter/shimmer vs reference)", voice_level, FLAG_LEVEL),
        ("voice_change", "Voice change vs your own baseline (step 4)", voice_change, FLAG_CHANGE),
        ("move_level", "Movement irregularity or guide deviation, steps 5-8 (provisional scale)", move_level, FLAG_LEVEL),
        ("move_change", "Movement change vs your own baseline (step 8)", move_change, FLAG_CHANGE),
    ]
    flags = [{"key": k, "label": label, "value": v, "threshold": thr,
              "flagged": v is not None and v >= thr} for k, label, v, thr in checks]
    n = sum(f["flagged"] for f in flags)
    code = "no_indicators" if n == 0 else "retest" if n == 1 else "see_doctor"
    info = VERDICTS[code]
    return {"code": code, "title": info["title"], "color": info["color"],
            "message": info["message"], "flags": flags, "flag_count": n}