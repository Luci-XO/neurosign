"""
movement_features.py - (t_ms, x, y) telemetry -> tremor / smoothness features.
Pipeline: sort+dedupe -> resample to 100 Hz -> 2 Hz high-pass -> Welch band power
-> velocity CV, jerk RMS -> distance from the displayed guide (spiral/wave).
"""
import numpy as np
from scipy import signal

RESAMPLE_HZ = 100.0
HIGHPASS_HZ = 2.0
MIN_SAMPLES = 50
MIN_DURATION_S = 2.0
MAX_GAP_S = 0.5   # a pause longer than this means the pen was lifted; we analyse the longest continuous stroke
REFERENCE_CANVAS_SIZE = (600, 400)
GUIDE_POINTS_PER_TURN = 720

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


def _reference_path(task_type, width, height):
    if task_type == "spiral":
        turns = 4
        angle = np.linspace(0, turns * 2 * np.pi, turns * GUIDE_POINTS_PER_TURN + 1)
        radius = (angle / (turns * 2 * np.pi)) * (min(width, height) / 2 - 20)
        return np.column_stack((
            width / 2 + radius * np.cos(angle),
            height / 2 + radius * np.sin(angle),
        ))
    if task_type == "wave":
        margin = 40
        x_ref = np.linspace(margin, width - margin, max(2, int((width - 2 * margin) / 2) + 1))
        y_ref = height / 2 + (height / 4) * np.sin(
            ((x_ref - margin) / (width - 2 * margin)) * 4 * np.pi
        )
        return np.column_stack((x_ref, y_ref))
    return None


def _smooth_path_deviation(x, y, task_type):
    if task_type == "free":
        return None
    window = max(5, len(x) // 20)
    window += window % 2 == 0
    if window >= len(x):
        return 0.0
    smooth_x = signal.savgol_filter(x, window, 3)
    smooth_y = signal.savgol_filter(y, window, 3)
    return float(np.mean(np.hypot(x - smooth_x, y - smooth_y)))


def _guide_deviation(x, y, task_type, canvas_size):
    """Compare equal arc-length progress points so adjacent spiral turns cannot mask drift."""
    if task_type == "free":
        return None
    width, height = canvas_size
    reference = _reference_path(task_type, width, height)
    if reference is None:
        return None

    def resample_by_progress(points, count):
        segment_lengths = np.hypot(*np.diff(points, axis=0).T)
        distance = np.concatenate(([0.0], np.cumsum(segment_lengths)))
        keep = np.concatenate(([True], np.diff(distance) > 1e-9))
        distance, points = distance[keep], points[keep]
        if len(points) < 2 or distance[-1] <= 0:
            return np.repeat(points[:1], count, axis=0)
        targets = np.linspace(0.0, distance[-1], count)
        return np.column_stack((
            np.interp(targets, distance, points[:, 0]),
            np.interp(targets, distance, points[:, 1]),
        ))

    count = min(1000, max(100, len(x)))
    trace = resample_by_progress(np.column_stack((x, y)), count)
    guide = resample_by_progress(reference, count)
    distances = np.hypot(trace[:, 0] - guide[:, 0], trace[:, 1] - guide[:, 1])
    return float(np.percentile(distances, 95))


def extract_movement_features(samples, task_type, canvas_size=REFERENCE_CANVAS_SIZE):
    if task_type not in ("spiral", "wave", "free"):
        raise MovementAnalysisError("Movement task was not recognized. Please try again.")
    if (
        not isinstance(canvas_size, (tuple, list))
        or len(canvas_size) != 2
        or any(not isinstance(value, (int, float)) or not np.isfinite(value) for value in canvas_size)
        or any(value < 100 or value > 4096 for value in canvas_size)
    ):
        raise MovementAnalysisError("Movement canvas size was invalid. Please restart the step.")
    canvas_size = tuple(float(value) for value in canvas_size)

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
    path_deviation = _smooth_path_deviation(x, y, task_type)
    guide_deviation = _guide_deviation(x, y, task_type, canvas_size)

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
        "path_deviation": None if path_deviation is None else round(path_deviation, 2),
        "guide_deviation": None if guide_deviation is None else round(guide_deviation, 2),
    }