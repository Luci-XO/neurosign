"""
movement_features.py - (t_ms, x, y) telemetry -> tremor / smoothness features.
Pipeline: sort+dedupe -> resample to 100 Hz -> 2 Hz high-pass -> Welch band power
-> velocity CV, jerk RMS -> path deviation (spiral/wave).
"""
import numpy as np
from scipy import signal

RESAMPLE_HZ = 100.0
HIGHPASS_HZ = 2.0
MIN_SAMPLES = 50
MIN_DURATION_S = 2.0
MAX_GAP_S = 0.5   # a pause longer than this means the pen was lifted; we analyse the longest continuous stroke

_trapz = getattr(np, "trapezoid", None) or np.trapz


class MovementAnalysisError(Exception):
    pass


def _clean(samples):
    arr = np.asarray(samples, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3 or not np.all(np.isfinite(arr)):
        raise MovementAnalysisError("Movement data was malformed. Please try again.")
    arr = arr[np.argsort(arr[:, 0], kind="stable")]
    _, keep = np.unique(arr[:, 0], return_index=True)   # drop duplicate timestamps
    return arr[np.sort(keep)]


def _longest_stroke(arr):
    """Split at long pauses (pointer lifted) and keep the longest continuous segment."""
    gaps = np.where(np.diff(arr[:, 0]) > MAX_GAP_S * 1000)[0]
    segments = np.split(arr, gaps + 1)
    return max(segments, key=lambda s: len(s))


def _highpass(series, hz):
    b, a = signal.butter(2, min(HIGHPASS_HZ / (hz / 2), 0.99), btype="highpass")
    padlen = min(3 * max(len(a), len(b)), len(series) - 1)
    return signal.filtfilt(b, a, series, padlen=padlen)


def _spectrum(xr, yr, hz):
    """Welch PSD of x and y residuals, SUMMED (not the magnitude: a magnitude signal
    hides circular tremor and doubles the apparent frequency of linear tremor)."""
    nper = min(256, len(xr))
    freqs, px = signal.welch(xr, fs=hz, nperseg=nper)
    _, py = signal.welch(yr, fs=hz, nperseg=nper)
    return freqs, px + py


def _band(freqs, psd, lo, hi):
    m = (freqs >= lo) & (freqs <= hi)
    if not m.any():
        return 0.0, 0.0
    return float(_trapz(psd[m], freqs[m])), float(freqs[m][np.argmax(psd[m])])


def _speed_jerk(x, y, hz):
    dt = 1.0 / hz
    vx, vy = np.gradient(x, dt), np.gradient(y, dt)
    speed = np.hypot(vx, vy)
    cv = float(speed.std() / speed.mean()) if speed.mean() > 1e-6 else 0.0
    jx = np.gradient(np.gradient(vx, dt), dt)
    jy = np.gradient(np.gradient(vy, dt), dt)
    return cv, float(np.sqrt(np.mean(jx ** 2 + jy ** 2)))


def _path_deviation(x, y, task_type):
    if task_type == "free":
        return None
    w = max(5, len(x) // 20)
    w += (w % 2 == 0)
    if w >= len(x):
        return 0.0
    sx, sy = signal.savgol_filter(x, w, 3), signal.savgol_filter(y, w, 3)
    return float(np.mean(np.hypot(x - sx, y - sy)))


def extract_movement_features(samples, task_type):
    if not isinstance(samples, list) or len(samples) < MIN_SAMPLES:
        raise MovementAnalysisError(
            f"Only {len(samples) if isinstance(samples, list) else 0} points captured. "
            f"Hold the mouse button and trace for longer (need at least {MIN_SAMPLES})."
        )
    arr = _longest_stroke(_clean(samples))
    if len(arr) < MIN_SAMPLES:
        raise MovementAnalysisError("Please trace in one continuous stroke without lifting the mouse button.")

    t = (arr[:, 0] - arr[0, 0]) / 1000.0
    duration = float(t[-1])
    if duration < MIN_DURATION_S:
        raise MovementAnalysisError(f"Stroke lasted only {duration:.1f}s. Trace for at least {MIN_DURATION_S:.0f}s.")

    tu = np.linspace(0, duration, int(duration * RESAMPLE_HZ))
    x, y = np.interp(tu, t, arr[:, 1]), np.interp(tu, t, arr[:, 2])

    freqs, psd = _spectrum(_highpass(x, RESAMPLE_HZ), _highpass(y, RESAMPLE_HZ), RESAMPLE_HZ)
    p46, f46 = _band(freqs, psd, 4, 6)
    p612, f612 = _band(freqs, psd, 6, 12)
    p_all, _ = _band(freqs, psd, 3, 12)
    share = p46 / p_all if p_all > 0 else 0.0     # scale-free: how much of the 3-12 Hz energy sits at 4-6 Hz
    cv, jerk = _speed_jerk(x, y, RESAMPLE_HZ)
    dev = _path_deviation(x, y, task_type)

    return {
        "task_type": task_type,
        "duration_s": round(duration, 3),
        "n_samples": int(len(arr)),
        "sample_rate_hz": RESAMPLE_HZ,
        "tremor_power_4_6": round(p46, 6),
        "tremor_power_6_12": round(p612, 6),
        "tremor_share": round(share, 4),
        "peak_freq_hz": round(f46 if p46 >= p612 else f612, 3),
        "velocity_cv": round(cv, 6),
        "jerk_rms": round(jerk, 6),
        "path_deviation": None if dev is None else round(dev, 4),
    }