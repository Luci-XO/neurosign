"""
voice_features.py - jitter, shimmer, HNR and F0 from a sustained vowel (Praat via parselmouth).
Includes quality checks so bad recordings are rejected with a clear message
instead of producing a meaningless score.
"""
import numpy as np
import parselmouth
from parselmouth.praat import call

MIN_DURATION_S = 2.0      # raw recording length
TRIM_S = 0.25             # cut button-click / onset / offset noise at both ends
MIN_PEAK = 0.02           # quieter than this = mic problem or silence
MAX_CLIP_FRACTION = 0.01  # >1% of samples at full scale = clipped
MIN_VOICED_FRACTION = 0.6


class VoiceAnalysisError(Exception):
    pass


def _safe(val):
    if val is None or val != val:
        return None
    return round(float(val), 6)


def extract_voice_features(wav_path: str) -> dict:
    try:
        sound = parselmouth.Sound(wav_path)
    except Exception:
        raise VoiceAnalysisError("Could not read the audio. Please record again.")

    duration = sound.get_total_duration()
    if duration < MIN_DURATION_S:
        raise VoiceAnalysisError(
            f"Recording is only {duration:.1f}s. Hold a steady 'aaah' for at least {MIN_DURATION_S:.0f}s (3s is best)."
        )

    samples = np.abs(sound.values)
    if samples.max() < MIN_PEAK:
        raise VoiceAnalysisError("Recording is almost silent. Check your microphone and speak closer to it.")
    if float(np.mean(samples > 0.98)) > MAX_CLIP_FRACTION:
        raise VoiceAnalysisError("Recording is clipped (too loud). Move back a little and try again.")

    sound = call(sound, "Extract part", TRIM_S, duration - TRIM_S, "rectangular", 1.0, False)

    pitch = call(sound, "To Pitch", 0.0, 75, 500)
    total_frames = call(pitch, "Get number of frames")
    voiced_frames = call(pitch, "Count voiced frames")
    if total_frames == 0 or voiced_frames / total_frames < MIN_VOICED_FRACTION:
        raise VoiceAnalysisError(
            "Could not detect a steady voice. Say a clear, continuous 'aaah' in a quiet room."
        )
    f0_mean = call(pitch, "Get mean", 0, 0, "Hertz")

    pp = call(sound, "To PointProcess (periodic, cc)", 75, 500)
    j = (0, 0, 0.0001, 0.02, 1.3)
    s = (0, 0, 0.0001, 0.02, 1.3, 1.6)
    try:
        out = {
            "f0_mean": f0_mean,
            "jitter_local": call(pp, "Get jitter (local)", *j),
            "jitter_rap": call(pp, "Get jitter (rap)", *j),
            "jitter_ppq5": call(pp, "Get jitter (ppq5)", *j),
            "jitter_ddp": call(pp, "Get jitter (ddp)", *j),
            "shimmer_local": call([sound, pp], "Get shimmer (local)", *s),
            "shimmer_db": call([sound, pp], "Get shimmer (local_dB)", *s),
            "shimmer_apq3": call([sound, pp], "Get shimmer (apq3)", *s),
            "shimmer_apq5": call([sound, pp], "Get shimmer (apq5)", *s),
            "shimmer_dda": call([sound, pp], "Get shimmer (dda)", *s),
            "hnr": call(call(sound, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0), "Get mean", 0, 0),
        }
    except Exception:
        raise VoiceAnalysisError("Could not measure jitter/shimmer. Please record a steadier 'aaah'.")

    out = {k: _safe(v) for k, v in out.items()}
    if any(v is None for v in out.values()):
        raise VoiceAnalysisError("Some measurements were undefined. Please record a steadier 'aaah'.")
    return out