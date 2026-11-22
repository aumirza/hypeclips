"""Timeline -> the windows the AI reads, written as chunk files with inline markers.

scan="hot": the strongest signal peaks (non-maximum suppressed), one window
each. scan="full": consecutive chunks over the whole stream.
"""

from __future__ import annotations

import pathlib

from .signals import BIN

MARK_ORDER = ("comments", "heatmap", "chat", "loud", "speech")


def hms(s: float) -> str:
    s = max(0, int(round(s)))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def hot(combined: list[float], k: int, window_sec: float, duration: float) -> list[dict]:
    order = sorted(range(len(combined)), key=lambda i: -combined[i])
    peaks: list[int] = []
    radius = window_sec / BIN
    for i in order:
        if combined[i] <= 0 or len(peaks) >= k:
            break
        if all(abs(i - p) >= radius for p in peaks):
            peaks.append(i)
    wins = []
    for p in sorted(peaks):
        t = p * BIN + BIN / 2
        a = max(0.0, t - 0.6 * window_sec)
        b = min(duration, a + window_sec)
        wins.append({"start": a, "end": b, "peak": t, "score": combined[p]})
    return wins


def full(duration: float, chunk_min: float) -> list[dict]:
    step = chunk_min * 60
    out, a = [], 0.0
    while a < duration:
        out.append({"start": a, "end": min(duration, a + step), "peak": None, "score": None})
        a += step
    return out


def _markers(i: int, series: dict, raw: dict) -> list[str]:
    tags = []
    s = lambda k: (series.get(k) or [0.0] * (i + 1))[i] if series.get(k) else 0.0  # noqa: E731
    if s("comments") >= 0.5:
        tags.append(f"CMT {s('comments'):.1f}")
    if s("heatmap") >= 1.5:
        tags.append(f"REPLAYED {s('heatmap'):.1f}")
    if s("chat") >= 0.8:
        tags.append(f"CHAT x{1 + s('chat'):.1f}")
    if s("loud") >= 0.75:
        tags.append(f"LOUD +{raw['loud_db_over'][i]:.0f}dB")
    if s("speech") >= 1.5:
        tags.append("FAST TALK")
    return tags


def write(wins: list[dict], lines: list[dict], series: dict, raw: dict, comments_by_bin: dict, out_dir: pathlib.Path,
          header: str, guide: str, romanize) -> list[pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("w*.md"):
        old.unlink()
    paths = []
    n = len(next(iter(series.values()))) if series else 0
    for wi, w in enumerate(wins, 1):
        name = f"w{wi:02d}"
        a_bin, b_bin = int(w["start"] // BIN), int(w["end"] // BIN)
        rows: list[tuple[float, str]] = []
        used_bins = set()
        for ln in lines:
            if ln["end"] <= w["start"] or ln["start"] >= w["end"]:
                continue
            b = int(ln["start"] // BIN)
            tags = _markers(b, series, raw) if b < n and b not in used_bins else []
            used_bins.add(b)
            text = romanize(ln["text"])
            rows.append((ln["start"], f"[{hms(ln['start'])}] {text}" + (f"   <<{' | '.join(tags)}>>" if tags else "")))
        for b in range(a_bin, min(b_bin + 1, n)):
            if b not in used_bins:  # strong moments without speech still show up
                tags = _markers(b, series, raw)
                if tags:
                    rows.append((b * BIN, f"[{hms(b * BIN)}] (no speech)   <<{' | '.join(tags)}>>"))
            for m in comments_by_bin.get(b, [])[:3]:
                rows.append((m["t"] + 0.01, f"[{hms(m['t'])}]   ~ comment ({m['likes']} likes): {m['text'][:100]}"))
        rows.sort(key=lambda r: r[0])
        sig = f" · signal {w['score']:.1f} peaking at {hms(w['peak'])}" if w.get("peak") is not None else ""
        body = [header, f"## Window {name}: {hms(w['start'])} to {hms(w['end'])}{sig}", "", guide,
                f"Write `picks/{name}.json` (a JSON array, `[]` when nothing qualifies).", ""]
        body += [r[1] for r in rows] or ["(no captions or signals in this window)"]
        p = out_dir / f"{name}.md"
        p.write_text("\n".join(body) + "\n", encoding="utf-8")
        paths.append(p)
        w["name"] = name
    return paths
