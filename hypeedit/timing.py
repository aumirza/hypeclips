"""Speed ramp: source-time beats -> HyperFrames `rate` lane + an exact time map.

Every overlay is placed in OUTPUT time, so all of moves.py goes through
TimeMap.out(source_t). Each speed change is a linear ramp centred on the
instant change, which advances the source by exactly the same amount, so
segment boundaries map exactly.
"""

from __future__ import annotations

from bisect import bisect_left

from .plan import Plan


def _paint(intervals, a, b, rate):
    out = []
    for s0, s1, r in intervals:
        if s1 <= a or s0 >= b:
            out.append((s0, s1, r))
            continue
        if s0 < a:
            out.append((s0, a, r))
        out.append((max(s0, a), min(s1, b), rate))
        if s1 > b:
            out.append((b, s1, r))
    return out


def source_segments(plan: Plan, src_dur: float, st: dict) -> tuple[list, tuple[float, float]]:
    """Piecewise-constant playback rate over source time; payoff slow-mo wins."""
    segs = [(0.0, src_dur, 1.0)]
    for b in plan.beats:
        if b.kind == "build":
            segs = _paint(segs, b.t, min(b.end, src_dur), st["build_rate"])
        elif b.kind == "lull":
            segs = _paint(segs, b.t, min(b.end, src_dur), st["lull_rate"])
    p = plan.payoff.t
    win = (max(0.0, p - st["slow_lead"] * st["slow_rate"]), min(src_dur, p + st["slow_tail"] * st["slow_rate"]))
    segs = _paint(segs, win[0], win[1], st["slow_rate"])
    merged = []
    for s in segs:
        if s[1] - s[0] < 1e-6:
            continue
        if merged and abs(merged[-1][2] - s[2]) < 1e-9:
            merged[-1] = (merged[-1][0], s[1], s[2])
        else:
            merged.append(s)
    return merged, win


def rate_points(segs, transition: float) -> list[tuple[float, float]]:
    pts = [(0.0, segs[0][2])]
    T = 0.0
    for i in range(len(segs) - 1):
        a0, a1, ra = segs[i]
        b0, b1, rb = segs[i + 1]
        T += (a1 - a0) / ra
        half = min(transition / 2, 0.4 * (a1 - a0) / ra, 0.4 * (b1 - b0) / rb)
        pts.append((round(T - half, 4), ra))
        pts.append((round(T + half, 4), rb))
    # drop points that do not move forward
    clean = [pts[0]]
    for t, v in pts[1:]:
        if t > clean[-1][0] + 1e-4:
            clean.append((t, v))
    return clean


class TimeMap:
    """Exact numeric map between source and output time for a rate lane."""

    DT = 1 / 1200

    def __init__(self, points: list[tuple[float, float]], src_dur: float):
        self.points = points
        outs, srcs = [0.0], [0.0]
        t = s = 0.0
        while s < src_dur:
            s += self.rate_at(t) * self.DT
            t += self.DT
            outs.append(t)
            srcs.append(s)
        self._outs, self._srcs = outs, srcs
        self.src_dur = src_dur

    def rate_at(self, t: float) -> float:
        p = self.points
        if t <= p[0][0]:
            return p[0][1]
        for (a, va), (b, vb) in zip(p, p[1:]):
            if a <= t <= b:
                return va + (vb - va) * (t - a) / (b - a)
        return p[-1][1]

    def out(self, src: float) -> float:
        i = min(bisect_left(self._srcs, src), len(self._srcs) - 1)
        return round(self._outs[i], 3)

    @property
    def duration(self) -> float:
        # stop a hair before the source runs out so the last frame is real
        return round(self.out(max(0.0, self.src_dur - 0.03)) - 0.005, 2)

    def lane(self) -> dict:
        return {"target": "rate", "points": [{"t": t, "v": round(v, 3)} for t, v in self.points]}


def build(plan: Plan, src_dur: float, st: dict):
    segs, win = source_segments(plan, src_dur, st)
    tm = TimeMap(rate_points(segs, st["ramp_transition"]), src_dur)
    return tm, segs, win
