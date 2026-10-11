"""Analyse du drift cardiaque intra-séance."""
import statistics


def analyse(hr_samples: list[dict]) -> dict:
    """
    Découpe la session en 3 tiers temporels égaux et calcule le drift FC.
    Retourne {} si données insuffisantes (< 30 samples ou < 20 min).
    """
    if len(hr_samples) < 30:
        return {}

    samples = sorted(hr_samples, key=lambda x: x["ts"])
    t0  = samples[0]["ts"]
    dur = samples[-1]["ts"] - t0

    if dur < 20 * 60:
        return {}

    third = dur / 3
    first = [s["bpm"] for s in samples if s["ts"] - t0 < third]
    mid   = [s["bpm"] for s in samples if third <= s["ts"] - t0 < 2 * third]
    last  = [s["bpm"] for s in samples if s["ts"] - t0 >= 2 * third]

    if not first or not last:
        return {}

    bpms  = [s["bpm"] for s in samples]
    m1    = statistics.mean(first)
    m3    = statistics.mean(last)
    return {
        "hr_first":  round(m1, 1),
        "hr_mid":    round(statistics.mean(mid), 1) if mid else None,
        "hr_last":   round(m3, 1),
        "hr_global": round(statistics.mean(bpms), 1),
        "hr_min":    min(bpms),
        "hr_max":    max(bpms),
        "drift_pct": round((m3 - m1) / m1 * 100, 1),
        "dur_min":   round(dur / 60, 1),
        "n_samples": len(samples),
    }


def derive_debut_fin(hr_samples: list[dict], fenetre_min: float = 20) -> dict:
    """
    FC moyenne des `fenetre_min` premières et dernières minutes de la séance.
    Retourne {} si la séance dure moins de 2 × fenetre_min (fenêtres qui se recouvrent)
    ou si l'une des fenêtres est vide.
    """
    samples = sorted(hr_samples, key=lambda x: x["ts"])
    if len(samples) < 2:
        return {}
    t0, t1 = samples[0]["ts"], samples[-1]["ts"]
    w = fenetre_min * 60
    if t1 - t0 < 2 * w:
        return {}
    first = [s["bpm"] for s in samples if s["ts"] - t0 < w]
    last  = [s["bpm"] for s in samples if t1 - s["ts"] < w]
    if not first or not last:
        return {}
    m1, m2 = statistics.mean(first), statistics.mean(last)
    return {
        "fc_debut": round(m1, 1),
        "fc_fin":   round(m2, 1),
        "derive_bpm": round(m2 - m1, 1),
    }


def time_series(hr_samples: list[dict], smooth_n: int = 60
                ) -> tuple[list[float], list[int], list[float]]:
    """
    Retourne (minutes_depuis_début, bpm_brut, bpm_lissé).
    smooth_n : demi-fenêtre de lissage (nombre de samples).
    """
    samples = sorted(hr_samples, key=lambda x: x["ts"])
    if not samples:
        return [], [], []

    t0   = samples[0]["ts"]
    x    = [(s["ts"] - t0) / 60 for s in samples]
    raw  = [s["bpm"] for s in samples]
    half = smooth_n // 2
    smooth = [
        sum(raw[max(0, i - half) : i + half + 1])
        / len(raw[max(0, i - half) : i + half + 1])
        for i in range(len(raw))
    ]
    return x, raw, smooth
