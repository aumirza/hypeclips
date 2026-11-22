"""Signals -> one timeline of 10 s bins, each signal scored 0-3 against its own baseline.

    speech   words per bin vs the surrounding 5 min (talking fast / a lot)
    loud     speaker loudness over the local baseline, only where someone is talking
    chat     chat messages vs baseline, shifted back for chat's reaction delay
    comments timestamp mentions in comments, weighted by likes
    heatmap  YouTube "most replayed"

A missing signal is simply absent; the combined score uses what exists.

There is deliberately no "game action" signal from audio: tested on a 9.8 h GTA stream against
frame-verified clips, no audio feature (high-band transients, stereo-side energy, crest) told
gunfights from driving. Action is found from the transcript and crowd signals, then confirmed
on the verify sheets.
"""

from __future__ import annotations

import math
import re
import statistics
import subprocess

BIN = 10.0


def nbins(duration: float) -> int:
    return int(duration // BIN) + 1


def _local_ratio(x: list[float], half=30, floor=1e-6) -> list[float]:
    out = []
    for i, v in enumerate(x):
        lo, hi = max(0, i - half), min(len(x), i + half + 1)
        base = statistics.median(x[lo:hi])
        out.append(v / max(base, floor))
    return out


def _clip(v, lo=0.0, hi=3.0):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- per source


def speech(lines: list[dict], n: int) -> tuple[list[float], list[float]]:
    words = [0.0] * n
    for ln in lines:
        b = min(n - 1, int(ln["start"] // BIN))
        words[b] += len(ln["text"].split())
    ratio = _local_ratio(words, floor=2.0)
    return words, [_clip(r - 1) if words[i] >= 4 else 0.0 for i, r in enumerate(ratio)]


def comments(mentions: list[dict], n: int) -> tuple[list[float], dict[int, list[dict]]]:
    w = [0.0] * n
    by_bin: dict[int, list[dict]] = {}
    for m in mentions:
        b = min(n - 1, int(m["t"] // BIN))
        # likes carry the weight; a 0-like comment counts a little; a comment listing
        # many timestamps (an index or spam) splits its weight across them
        weight = (0.3 + math.log1p(m["likes"])) / max(1, m.get("n", 1))
        for k, f in ((b, 1.0), (b + 1, 0.6), (b + 2, 0.3)):  # people timestamp the start of a moment
            if k < n:
                w[k] += weight * f
        by_bin.setdefault(b, []).append(m)
    nz = sorted(v for v in w if v > 0)
    ref = nz[int(0.9 * (len(nz) - 1))] if nz else 1.0
    return [_clip(v / ref * 2) for v in w], by_bin


def chat(times: list[float], n: int, lag=10.0) -> list[float]:
    if len(times) < 50:
        return []
    c = [0.0] * n
    for t in times:
        b = int(max(0.0, t - lag) // BIN)
        if b < n:
            c[b] += 1
    return [_clip(r - 1) if c[i] >= 8 else 0.0 for i, r in enumerate(_local_ratio(c, floor=1.0))]


def heatmap(points: list[dict] | None, n: int) -> list[float]:
    if not points:
        return []
    h = [0.0] * n
    for p in points:
        for b in range(int(p["start_time"] // BIN), min(n, int(p["end_time"] // BIN) + 1)):
            h[b] = max(h[b], float(p["value"]))
    top = max(h) or 1.0
    return [_clip(v / top * 3) for v in h]


def _astats(path, sr: int, frame: int, pre: str, key: str) -> list[float]:
    af = (pre + "," if pre else "") + f"asetnsamples=n={frame},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.{key}:file=-"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-ac", "1", "-ar", str(sr), "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = []
    for m in re.finditer(rf"{key}=(-?[\d.]+|-inf)", r.stdout):
        v = m.group(1)
        vals.append(-90.0 if v == "-inf" else float(v))
    return vals


def _scan(path) -> list[float]:
    """Loudness per second. Fast path: one decode + numpy in the project venv
    (pipeline/research/audioscan.py); fallback: ffmpeg astats (slower, no numpy needed)."""
    import json
    import pathlib
    import tempfile

    from ..stages import ROOT, VENV_BIN

    py = VENV_BIN / "python"
    if py.exists():
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "scan.json"
            r = subprocess.run([str(py), "-m", "pipeline.research.audioscan", str(path), str(out)], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode == 0 and out.exists():
                return json.loads(out.read_text())["rms_db"]
    return _astats(path, 8000, 8000, "", "RMS_level")


def audio(path, n: int, words: list[float]) -> tuple[list[float], dict]:
    """Speaker loudness per bin (only where someone is talking) + dB-over-baseline for markers."""
    rms = _scan(path)
    loud_db = [-90.0] * n
    for sec, v in enumerate(rms):
        b = int(sec // BIN)
        if b < n:
            loud_db[b] = max(loud_db[b], v)
    over = []
    for i, v in enumerate(loud_db):
        lo, hi = max(0, i - 18), min(n, i + 19)
        over.append(v - statistics.median(loud_db[lo:hi]))
    loud = [_clip(d / 4) if words[i] > 0 and loud_db[i] > -35 else 0.0 for i, d in enumerate(over)]
    return loud, {"loud_db_over": over}


# ---------------------------------------------------------------- combine


def combine(series: dict[str, list[float]], weights: dict[str, float], n: int) -> list[float]:
    raw = [0.0] * n
    for name, s in series.items():
        if not s:
            continue
        w = float(weights.get(name, 1.0))
        for i in range(n):
            raw[i] += w * s[i]
    return [round(0.25 * raw[max(0, i - 1)] + 0.5 * raw[i] + 0.25 * raw[min(n - 1, i + 1)], 3) for i in range(n)]
