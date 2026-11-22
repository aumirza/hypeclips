"""Move library: beats (already mapped to output time) -> camera tweens, overlays and sound cues.

Each move is one function. A move adds to an Edit; project.py turns the Edit
into HyperFrames HTML. Move names match the vocabulary in
.claude/skills/hype-edit/references/vocabulary.md.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field

from .plan import FRAME_H, FRAME_W, Plan

# sfx file -> seconds from its start to its peak (see assets/sfx/CREDITS.md)
SFX_PEAK = {
    "riser.mp3": 3.472,
    "impact-bass-1.mp3": 0.073,
    "glitch-1.mp3": 0.2,  # onset; its swell follows the stamp
    "glitch-2.mp3": 0.022,
    "whoosh.mp3": 0.162,
    "whoosh-short.mp3": 0.162,
}
SFX_LEN = {
    "riser.mp3": 10.03,
    "impact-bass-1.mp3": 2.12,
    "glitch-1.mp3": 2.64,
    "glitch-2.mp3": 3.5,
    "whoosh.mp3": 0.575,
    "whoosh-short.mp3": 0.575,
}
FRAME = 1 / 30
SFX_TRACK = {"whoosh": 3, "riser": 4, "boom": 5, "glitch": 6}


@dataclass
class Cue:
    id: str
    file: str
    start: float
    vol: float
    track: int
    dur: float | None = None
    media_start: float = 0.0
    fade_out: float = 0.0


@dataclass
class Overlay:
    id: str
    start: float
    dur: float
    html: str
    js: list[str]
    attrs: str = ""
    comment: str = ""


@dataclass
class Edit:
    dur: float
    st: dict
    focus: tuple[float, float]
    zoom: list[str] = field(default_factory=list)  # root JS lines on #zoom
    jolts: list[tuple[float, float, float]] = field(default_factory=list)
    grade_js: list[str] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    cues: list[Cue] = field(default_factory=list)
    game_lane: list[dict] = field(default_factory=list)
    music: dict | None = None
    log: list[str] = field(default_factory=list)
    marks: dict = field(default_factory=dict)  # named output times for review/snapshots

    def cue(self, kind: str, file: str, peak_at: float, vol: float, dur: float | None = None, fade_out=0.0):
        """Place a sound so its peak lands one frame after the picture event at peak_at."""
        start = peak_at + FRAME - SFX_PEAK[file]
        media_start = 0.0
        if start < 0:
            media_start, start = -start, 0.0
        length = SFX_LEN[file] - media_start if dur is None else dur
        length = min(length, self.dur - start)
        if length <= 0.05:
            return
        n = sum(1 for c in self.cues if c.id.startswith(f"sfx-{kind}")) + 1
        self.cues.append(Cue(f"sfx-{kind}-{n}", file, round(start, 3), vol, SFX_TRACK[kind], round(length, 3), round(media_start, 3), fade_out))

    def whoosh(self, at: float, vol_scale=1.0):
        if any(abs(c.start - (at + FRAME - 0.162)) < 0.45 for c in self.cues if c.id.startswith("sfx-whoosh")):
            return
        n = sum(1 for c in self.cues if c.id.startswith("sfx-whoosh"))
        f = "whoosh.mp3" if n % 2 == 0 else "whoosh-short.mp3"
        self.cue("whoosh", f, at, round(self.st["levels"]["whoosh"] * vol_scale, 3))


def _r(x: float) -> float:
    return round(x, 3)


def _fit(text: str, base: int, max_w: int, glyph=0.74) -> int:
    return int(min(base, max_w / max(1, len(text)) / glyph))


def _t(s: str) -> str:
    return html.escape(s, quote=True)


# ------------------------------------------------------------------ moves


def ramp(e: Edit, tm, win):
    """Speed ramp: the rate lane itself lives on the video; here the game audio ducks under the slow-mo."""
    lv = e.st["levels"]
    s0, s1 = tm.out(win[0]), tm.out(win[1])
    g = lv["game_slowmo"]
    e.game_lane = [{"t": 0, "v": 1}, {"t": _r(s0 - 0.1), "v": 1}, {"t": _r(s0 + 0.05), "v": g},
                   {"t": _r(s1 - 0.05), "v": g}, {"t": _r(s1 + 0.25), "v": 1}]
    e.marks.update(slow_in=s0, slow_out=s1)


def hook(e: Edit, lines: list[str], whips: list[float], build_in: float | None):
    """Frame-0 title: both lines on screen at frame 0 (the thumbnail), slam-settle, exits on the first whip."""
    st = e.st["text"]
    words = sum(len(x.split()) for x in lines)
    hold = 0.5 + 0.3 * words
    exit_at = next((w - 0.12 for w in whips if hold <= w <= 2.8), None)
    if exit_at is None:
        exit_at = max(hold, 1.6)
        if build_in is not None and build_in - 0.2 > hold:
            exit_at = min(exit_at, build_in - 0.2)
    sizes = st["hook_sizes"]
    top, main = (lines[0], lines[1]) if len(lines) == 2 else (None, lines[0])
    parts = []
    js = []
    if top:
        fs = _fit(top, sizes[0], st["max_text_width"])
        parts.append(f'<div id="fx-hook-top" class="fx-display" style="font-size:{fs}px" data-var-text="hook_top">{_t(top)}</div>')
        js.append('tl.fromTo("#fx-hook-top", { scale: 1.12, opacity: 1 }, { scale: 1, duration: 0.22, ease: "expo.out" }, 0);')
    fs = _fit(main, sizes[1], st["max_text_width"])
    parts.append(f'<div id="fx-hook-main" class="fx-display fx-accent" style="font-size:{fs}px" data-var-text="hook_main">{_t(main)}</div>')
    js.append('tl.fromTo("#fx-hook-main", { scale: 1.3, opacity: 1 }, { scale: 1, duration: 0.26, ease: "expo.out" }, 0);')
    js.append(f'tl.to("#fx-hook-wrap", {{ x: -260, opacity: 0, filter: "blur(16px)", duration: 0.2, ease: "power3.in" }}, {_r(exit_at)});')
    e.overlays.append(Overlay("fx-hook", 0, _r(exit_at + 0.27),
                              '<div id="fx-hook-wrap" class="fx-stack" style="top:320px">' + "".join(parts) + "</div>",
                              js, "data-layout-allow-overflow", "hook: on screen from frame 0, whips off"))
    e.whoosh(exit_at + 0.1)
    e.marks["hook_exit"] = _r(exit_at)


def tease(e: Edit, text: str, build_in: float, until: float):
    """Bar text over the sped-up build ('WAIT FOR IT')."""
    start, end = build_in + 0.05, until - 0.18
    if end - start < 1.0:
        e.log.append("tease skipped: build too short on screen")
        return
    st = e.st["text"]
    js = [f'tl.fromTo("#fx-tease", {{ opacity: 0, x: -40, filter: "blur(8px)" }}, {{ opacity: 1, x: 0, filter: "blur(0px)", duration: 0.22, ease: "power4.out" }}, {_r(start)});',
          f'tl.to("#fx-tease", {{ opacity: 0, filter: "blur(8px)", duration: 0.15, ease: "power2.in" }}, {_r(end - 0.15)});']
    fs = min(58, int(st["max_text_width"] / max(1, len(text)) / 0.62))
    e.overlays.append(Overlay("fx-teaser", _r(start), _r(end - start + 0.02),
                              f'<div id="fx-tease-wrap"><div id="fx-tease" style="font-size:{fs}px" data-var-text="tease">{_t(text)}</div></div>',
                              js, "", "tease through the build"))
    e.marks["tease"] = _r(start + 0.4)


def payoff(e: Edit, P: float, focus, lock: bool, stamp: str):
    """The one big moment: letterbox, punch, lock, flash, jolt, stamp, riser, boom."""
    st, lv = e.st, e.st["levels"]
    s_in, s_out = e.marks["slow_in"], e.marks["slow_out"]
    fx, fy = focus
    # letterbox
    lb_in, lb_out = P - 0.6, s_out - 0.03
    e.overlays.append(Overlay("fx-letterbox", _r(lb_in), _r(lb_out - lb_in + 0.22),
                              '<div id="fx-bar-top" class="fx-bar"></div><div id="fx-bar-bot" class="fx-bar"></div>',
                              [f'tl.fromTo("#fx-bar-top", {{ yPercent: -100 }}, {{ yPercent: 0, duration: 0.25, ease: "power3.out" }}, {_r(lb_in)});',
                               f'tl.fromTo("#fx-bar-bot", {{ yPercent: 100 }}, {{ yPercent: 0, duration: 0.25, ease: "power3.out" }}, {_r(lb_in)});',
                               f'tl.to("#fx-bar-top", {{ yPercent: -100, duration: 0.2, ease: "power3.in" }}, {_r(lb_out)});',
                               f'tl.to("#fx-bar-bot", {{ yPercent: 100, duration: 0.2, ease: "power3.in" }}, {_r(lb_out)});'],
                              "data-layout-ignore", "kill-cam letterbox"))
    # punch
    k = st["punch"]
    e.zoom += [f'tl.fromTo("#zoom", {{ scale: 1 }}, {{ scale: {k}, duration: 0.5, ease: "power2.inOut", immediateRender: false }}, {_r(P - 0.55)});',
               f'tl.to("#zoom", {{ scale: {_r(k * st["punch_kick"])}, duration: 0.07, ease: "power4.out" }}, {_r(P)});',
               f'tl.to("#zoom", {{ scale: {_r(k * st["punch_settle"])}, duration: 0.6, ease: "expo.out" }}, {_r(P + 0.07)});',
               f'tl.to("#zoom", {{ scale: 1, duration: 0.3, ease: "power3.in" }}, {_r(s_out - 0.07)});']
    e.whoosh(s_out + 0.2)
    # lock
    if lock:
        x, y = min(max(fx - 130, 0), FRAME_W - 260), min(max(fy - 130, 0), FRAME_H - 260)
        corners = "".join(f'<div class="fx-corner fx-c-{c}"></div>' for c in ("tl", "tr", "bl", "br"))
        e.overlays.append(Overlay("fx-lock", _r(P - 0.5), 0.55,
                                  f'<div id="fx-lock-box" style="left:{x:.0f}px;top:{y:.0f}px">{corners}</div>',
                                  [f'tl.fromTo("#fx-lock-box", {{ scale: 1.9, opacity: 0, rotation: 12 }}, {{ scale: 1, opacity: 1, rotation: 0, duration: 0.3, ease: "expo.out" }}, {_r(P - 0.5)});',
                                   f'tl.to("#fx-lock-box", {{ scale: 0.82, duration: 0.08, ease: "power2.out" }}, {_r(P - 0.13)});',
                                   f'tl.to("#fx-lock-box .fx-corner", {{ borderColor: "var(--accent)", duration: 0.04, ease: "none" }}, {_r(P - 0.13)});'],
                                  "data-layout-ignore", "target lock on the focus"))
    # flash (drawn under the letterbox: overlays are painted in list order, see project.py)
    e.overlays.append(Overlay("fx-flash", _r(P - 0.02), 0.3, '<div id="fx-flash-fill" class="fx-full"></div>',
                              [f'tl.fromTo("#fx-flash-fill", {{ opacity: 0 }}, {{ opacity: 0.92, duration: 0.03, ease: "none" }}, {_r(P - 0.02)});',
                               f'tl.to("#fx-flash-fill", {{ opacity: 0, duration: 0.24, ease: "expo.out" }}, {_r(P + 0.02)});'],
                              "data-layout-ignore", "impact flash"))
    e.grade_js += [f'tl.to("#a-roll", {{ "--hf-color-grading-exposure": {st["flash_exposure"]}, "--hf-color-grading-bloom": {st["flash_bloom"]}, duration: 0.03, ease: "none" }}, {_r(P - 0.02)});',
                   f'tl.to("#a-roll", {{ "--hf-color-grading-exposure": 0, "--hf-color-grading-bloom": 0, duration: 0.45, ease: "expo.out" }}, {_r(P + 0.02)});']
    e.jolts.append((P, *st["jolt_payoff"]))
    # stamp: above the focus, or below it when the focus sits high
    stamp_h = 220
    top = fy - 475 if fy - 475 >= 300 else fy + 200
    top = min(top, 1330 - stamp_h)
    fs = _fit(stamp, st["text"]["stamp_size"], st["text"]["max_text_width"])
    layers = "".join(
        f'<div id="fx-stamp-{n}" class="fx-stamp-layer fx-display{cls}" style="font-size:{fs}px" data-var-text="stamp">{_t(stamp)}</div>'
        for n, cls in (("c", ""), ("r", ""), ("main", " fx-accent")))
    t0 = P + 0.02
    e.overlays.append(Overlay("fx-stamp", _r(t0), _r(s_out + 0.2 - t0),
                              f'<div id="fx-stamp-wrap" style="top:{top:.0f}px">{layers}</div>',
                              [f'tl.fromTo("#fx-stamp-wrap", {{ scale: 2.3, rotation: -9, opacity: 0 }}, {{ scale: 1, rotation: -5, opacity: 1, duration: 0.2, ease: "expo.out" }}, {_r(t0)});',
                               f'tl.fromTo("#fx-stamp-r", {{ opacity: 0.9, x: 22, y: -6 }}, {{ opacity: 0, x: 0, y: 0, duration: 0.45, ease: "power3.out" }}, {_r(t0 + 0.03)});',
                               f'tl.fromTo("#fx-stamp-c", {{ opacity: 0.9, x: -22, y: 6 }}, {{ opacity: 0, x: 0, y: 0, duration: 0.45, ease: "power3.out" }}, {_r(t0 + 0.03)});',
                               f'tl.to("#fx-stamp-wrap", {{ scale: 1.2, opacity: 0, filter: "blur(14px)", duration: 0.2, ease: "power3.in" }}, {_r(s_out - 0.07)});'],
                              "data-layout-allow-overflow data-layout-allow-overlap", "payoff stamp"))
    # sound
    e.cue("riser", "riser.mp3", P, lv["riser"], dur=3.9 if P > 3.6 else None, fade_out=0.3)
    e.cue("boom", "impact-bass-1.mp3", P, lv["boom"])
    e.cue("glitch", "glitch-1.mp3", P + 0.1, lv["glitch_stamp"], dur=1.2, fade_out=0.3)
    e.marks.update(payoff=_r(P), stamp=_r(P + 0.3))


def hits(e: Edit, hit_beats: list[tuple[float, bool]]):
    """Secondary impacts: jolts, a shared quick punch per cluster, red damage when hurt."""
    st, lv = e.st, e.st["levels"]
    busy = (e.marks["payoff"] - 0.8, e.marks["slow_out"] + 0.45)
    hit_beats = [(t, hurt) for t, hurt in hit_beats if not busy[0] <= t <= busy[1]]
    clusters: list[list[tuple[float, bool]]] = []
    for h in hit_beats:
        if clusters and h[0] - clusters[-1][-1][0] <= st["hit_cluster"]:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    for ci, cl in enumerate(clusters):
        first, last = cl[0][0], cl[-1][0]
        a, b = first - 0.45, last + 0.15
        if a > busy[1] or b < busy[0]:
            e.zoom += [f'tl.fromTo("#zoom", {{ scale: 1 }}, {{ scale: {st["hit_punch"]}, duration: 0.22, ease: "power3.out", immediateRender: false }}, {_r(a)});',
                       f'tl.to("#zoom", {{ scale: 1, duration: 0.16, ease: "power3.in" }}, {_r(b)});']
            e.whoosh(b + 0.12, 0.85)
        for t, hurt in cl:
            if hurt:
                e.jolts.append((t, *st["jolt_hurt"]))
                oid = f"fx-dmg-{ci}-{int(t * 100)}"
                e.overlays.append(Overlay(oid, _r(t - 0.01), 0.5, f'<div id="{oid}-fill" class="fx-full fx-dmg-fill"></div>',
                                          [f'tl.fromTo("#{oid}-fill", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.04, ease: "none" }}, {_r(t - 0.01)});',
                                           f'tl.to("#{oid}-fill", {{ opacity: 0, duration: 0.4, ease: "power2.out" }}, {_r(t + 0.05)});'],
                                          "data-layout-ignore", "player hit"))
                e.grade_js += [f'tl.to("#a-roll", {{ "--hf-color-grading-exposure": {st["hurt_exposure"]}, duration: 0.03, ease: "none" }}, {_r(t - 0.01)});',
                               f'tl.to("#a-roll", {{ "--hf-color-grading-exposure": 0, duration: 0.35, ease: "power2.out" }}, {_r(t + 0.03)});']
                e.cue("glitch", "glitch-2.mp3", t, lv["glitch_hurt"], dur=0.6, fade_out=0.25)
            else:
                e.jolts.append((t, *st["jolt_hit"]))
        e.marks[f"hits_{ci + 1}"] = _r(last)


def whips(e: Edit, times: list[float]):
    """In-game fast camera moves: a whoosh on each."""
    for t in times:
        e.whoosh(t)


def outro(e: Edit, lines: list[str]):
    """Closing question held >= 2 s, words blur in, then dead still."""
    st = e.st["text"]
    start = e.dur - e.st["outro_hold"]
    if start < e.marks.get("slow_out", 0) + 1.0:
        e.log.append("outro skipped: not enough runtime after the payoff")
        return
    top, main = (lines[0], lines[1]) if len(lines) == 2 else (None, lines[0])
    parts, js = [], []
    if top:
        fs = _fit(top, st["outro_sizes"][0], st["max_text_width"])
        parts.append(f'<div id="fx-outro-top" class="fx-display" style="font-size:{fs}px" data-var-text="outro_top">{_t(top)}</div>')
        js.append(f'tl.fromTo("#fx-outro-top", {{ opacity: 0, filter: "blur(10px)", scale: 1.15 }}, {{ opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.18, ease: "power4.out" }}, {_r(start + 0.01)});')
    fs = _fit(main, st["outro_sizes"][1], st["max_text_width"])
    parts.append(f'<div id="fx-outro-main" class="fx-display fx-accent" style="font-size:{fs}px" data-var-text="outro_main">{_t(main)}</div>')
    js.append(f'tl.fromTo("#fx-outro-main", {{ opacity: 0, filter: "blur(10px)", scale: 1.6 }}, {{ opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.24, ease: "expo.out" }}, {_r(start + 0.13)});')
    e.overlays.append(Overlay("fx-outro", _r(start), _r(e.dur - start),
                              '<div id="fx-outro-wrap" class="fx-stack" style="top:300px">' + "".join(parts) + "</div>",
                              js, "", "closing question"))
    e.whoosh(start + 0.1, 0.75)
    e.marks["outro"] = _r(start + 0.6)


def bed(e: Edit, media_start: float, P: float):
    """Music bed: dip just before the payoff, the drop lands on it."""
    lv = e.st["levels"]
    ml = lv["music_lane"]
    e.music = {"media_start": _r(media_start), "vol": lv["music"],
               "lane": [{"t": 0, "v": ml["base"]}, {"t": _r(P - 0.65), "v": ml["base"]}, {"t": _r(P - 0.45), "v": ml["dip"]},
                        {"t": _r(P - 0.05), "v": ml["dip"]}, {"t": _r(P), "v": ml["drop"]}, {"t": _r(e.dur - 1.0), "v": ml["drop"]}]}


# ------------------------------------------------------------------ assemble


def compose(plan: Plan, tm, win, st: dict, music_start: float | None) -> Edit:
    P = tm.out(plan.payoff.t)
    focus = plan.payoff.focus or (FRAME_W / 2, FRAME_H / 2)
    e = Edit(dur=tm.duration, st=st, focus=focus)
    whip_t = [tm.out(b.t) for b in plan.of_kind("whip")]
    builds = plan.of_kind("build")
    build_in = tm.out(builds[0].t) if builds else None

    ramp(e, tm, win)
    hook(e, plan.text.hook, whip_t, build_in)
    if plan.text.tease and builds:
        b = builds[0]
        tease(e, plan.text.tease, tm.out(b.t), min(tm.out(b.end) + 1.0, P - 0.6))
    payoff(e, P, focus, plan.payoff.lock, plan.text.stamp)
    hits(e, [(tm.out(b.t), b.hurt) for b in plan.of_kind("hit")])
    whips(e, whip_t)
    if plan.text.outro:
        outro(e, plan.text.outro)
    if music_start is not None:
        bed(e, music_start, P)

    g = 10 ** (plan.mix_gain_db / 20)
    for c in e.cues:
        c.vol = _r(c.vol * g)
    e.log.append(f"payoff at {P:.2f}s output, slow-mo {e.marks['slow_in']:.2f}-{e.marks['slow_out']:.2f}s, runtime {e.dur:.2f}s")
    return e


def fx_variables(plan: Plan) -> str:
    t = plan.text
    hook_top, hook_main = (t.hook[0], t.hook[1]) if len(t.hook) == 2 else ("", t.hook[0])
    out_top, out_main = ((t.outro[0], t.outro[1]) if len(t.outro) == 2 else ("", t.outro[0])) if t.outro else ("", "")
    v = [("hook_top", "Hook line 1", hook_top), ("hook_main", "Hook line 2", hook_main), ("tease", "Tease line", t.tease or ""),
         ("stamp", "Payoff stamp", t.stamp), ("outro_top", "Outro line 1", out_top), ("outro_main", "Outro line 2", out_main)]
    decl = [{"id": i, "type": "string", "label": lab, "default": d} for i, lab, d in v]
    decl.append({"id": "accent", "type": "color", "label": "Accent", "default": t.accent})
    return json.dumps(decl)
