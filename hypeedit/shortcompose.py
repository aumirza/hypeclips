"""Multi-clip shorts: rendered segments -> one HyperFrames project (montage or ranking).

Each segment is a clip already rendered with its own edit in segment mode (slow-mo,
punch, stamp, game audio and sfx; no hook, outro or music). The short adds what
belongs to the whole: the frame-0 title, the cuts, the rank slams, one music bed
with its drop, and the closing question.
"""

from __future__ import annotations

import html
import json
import pathlib
import shutil

from . import media
from .moves import FRAME, SFX_LEN, SFX_PEAK
from .project import LIB, _attr_json

CSS = """
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #000; }
      .seg { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; object-fit: cover; }
"""

FX_CSS = """
        #root { position: absolute; inset: 0; pointer-events: none; color: #fff; --accent: %(accent)s; }
        .fx-full { position: absolute; inset: 0; }
        .fx-display { font-family: "Archivo Black", sans-serif; text-transform: uppercase; line-height: 0.9; letter-spacing: -1px;
          text-align: center; -webkit-text-stroke: 3px #000; paint-order: stroke fill;
          text-shadow: 0 10px 0 rgba(0,0,0,0.55), 0 0 40px rgba(0,0,0,0.45); }
        .fx-accent { color: var(--accent); }
        .fx-stack { position: absolute; left: 70px; right: 170px; display: flex; flex-direction: column; align-items: center; gap: 14px; }
        #sc-header { position: absolute; left: 70px; right: 170px; top: 190px; display: flex; justify-content: center; }
        #sc-header-pill { background: var(--accent); color: #fff; padding: 14px 30px 12px; border-radius: 14px;
          font-family: "Archivo Black", sans-serif; text-transform: uppercase; white-space: nowrap;
          box-shadow: 0 10px 30px rgba(0,0,0,0.45); }
        .sc-rank { position: absolute; left: 0; right: 100px; top: 560px; display: flex; justify-content: center; }
        .sc-rank-num { font-size: 280px; background: var(--accent); color: #fff; padding: 10px 46px 0; border-radius: 48px;
          box-shadow: 0 16px 50px rgba(0,0,0,0.5); }
        .sc-rank-num.sc-top { background: #fff; color: var(--accent); }
        .sc-flash { background: #fff; opacity: 0; }
"""


TRACK = {"whoosh": 10, "boom": 11, "riser": 12}  # one Studio lane per kind of sound


def _t(s: str) -> str:
    return html.escape(s, quote=True)


def _r(x: float) -> float:
    return round(x, 3)


def _fit(text: str, base: int, max_w: int = 800, glyph=0.74) -> int:
    return int(min(base, max_w / max(1, len(text)) / glyph))


def build(out_dir: pathlib.Path, fmt: str, segments: list[dict], texts: dict, music: pathlib.Path | None,
          accent: str, levels: dict | None = None) -> dict:
    """segments: [{path, payoff (s into the segment) | None, rank (ranking only)}] in play order.
    texts: {header, hook: [l1, l2], outro: [l1, l2]}. Returns {duration, marks, log}."""
    lv = {"music": 0.2, "boom": 0.3, "whoosh": 0.28, "riser": 0.09, **(levels or {})}
    d = out_dir
    if not (d / "hyperframes.json").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        media.run(["npx", "hyperframes", "init", d.name, "--example", "blank", "--resolution", "portrait",
                   "--non-interactive", "--skip-skills", "--skill", "hyperframes"], cwd=d.parent)
    (d / "assets" / "sfx").mkdir(parents=True, exist_ok=True)
    (d / "compositions").mkdir(exist_ok=True)

    # ---- timeline
    t, segs = 0.0, []
    for i, s in enumerate(segments):
        dur = round(media.probe(s["path"])["duration"] - 0.02, 3)
        name = f"seg_{i + 1:02d}.mp4"
        dst = d / "assets" / name
        if not dst.exists() or dst.stat().st_size != pathlib.Path(s["path"]).stat().st_size:
            shutil.copy2(s["path"], dst)
        segs.append({**s, "file": name, "start": round(t, 3), "dur": dur})
        t += dur
    total = round(t, 2)
    log, marks, cues, overlays = [], {}, [], []

    def cue(kind, file, peak_at, vol, dur=None, fade=0.0):
        start = peak_at + FRAME - SFX_PEAK[file]
        ms = 0.0
        if start < 0:
            ms, start = -start, 0.0
        length = min((SFX_LEN[file] - ms) if dur is None else dur, total - start)
        if length > 0.05:
            cues.append({"id": f"sc-{kind}-{len(cues) + 1}", "file": file, "start": _r(start), "dur": _r(length),
                         "ms": _r(ms), "vol": vol, "fade": fade})
            shutil.copy2(LIB / "assets" / "sfx" / file, d / "assets" / "sfx" / file)

    # ---- cuts: a flash and a whoosh on every boundary
    for i, s in enumerate(segs[1:], 1):
        a = s["start"]
        overlays.append((f"sc-flash-{i}", a - 0.03, 0.3, f'<div id="sc-flash-{i}-f" class="fx-full sc-flash"></div>',
                         [f'tl.fromTo("#sc-flash-{i}-f", {{ opacity: 0 }}, {{ opacity: 0.85, duration: 0.03, ease: "none" }}, {_r(a - 0.03)});',
                          f'tl.to("#sc-flash-{i}-f", {{ opacity: 0, duration: 0.22, ease: "expo.out" }}, {_r(a + 0.01)});']))
        cue("whoosh", "whoosh.mp3" if i % 2 else "whoosh-short.mp3", a - 0.05, lv["whoosh"])

    # ---- format layers
    if fmt == "ranking":
        header = texts.get("header") or ""
        if header:
            fs = _fit(header, 64, 660, 0.7)
            overlays.append(("sc-hdr", 0.0, total, f'<div id="sc-header"><div id="sc-header-pill" style="font-size:{fs}px" data-var-text="header">{_t(header)}</div></div>',
                             ['tl.fromTo("#sc-header-pill", { scale: 1.15 }, { scale: 1, duration: 0.25, ease: "expo.out" }, 0);']))
        for i, s in enumerate(segs):
            a, rank = s["start"], s.get("rank") or (len(segs) - i)
            oid = f"sc-rank-{rank}"
            overlays.append((oid, a, s["dur"], f'<div class="sc-rank" id="{oid}-wrap"><div class="sc-rank-num fx-display{" sc-top" if rank == 1 else ""}" id="{oid}-n">#{rank}</div></div>',
                             [f'tl.fromTo("#{oid}-n", {{ scale: 2.2, opacity: 0, rotation: -6 }}, {{ scale: 1, opacity: 1, rotation: -4, duration: 0.2, ease: "expo.out" }}, {_r(a)});',
                              # settles into a corner badge under the header, where it stays for the segment
                              f'tl.to("#{oid}-wrap", {{ x: -275, y: -295, scale: 0.36, duration: 0.35, ease: "power3.inOut" }}, {_r(a + 0.75)});']))
            cue("boom", "impact-bass-1.mp3", a + 0.02, lv["boom"])
            marks[f"rank_{rank}"] = _r(a + 0.3)
        last = segs[-1]
        cue("riser", "riser.mp3", last["start"], lv["riser"], dur=min(3.9, last["start"] + 0.3) if last["start"] > 1 else None, fade=0.3)
        drop_at = last["start"]
    else:
        hook = texts.get("hook") or []
        if hook:
            top, main = (hook[0], hook[1]) if len(hook) == 2 else (None, hook[0])
            parts, js = [], []
            if top:
                parts.append(f'<div id="sc-hook-top" class="fx-display" style="font-size:{_fit(top, 66)}px" data-var-text="hook_top">{_t(top)}</div>')
                js.append('tl.fromTo("#sc-hook-top", { scale: 1.12, opacity: 1 }, { scale: 1, duration: 0.22, ease: "expo.out" }, 0);')
            parts.append(f'<div id="sc-hook-main" class="fx-display fx-accent" style="font-size:{_fit(main, 118)}px" data-var-text="hook_main">{_t(main)}</div>')
            js.append('tl.fromTo("#sc-hook-main", { scale: 1.3, opacity: 1 }, { scale: 1, duration: 0.26, ease: "expo.out" }, 0);')
            hold = 0.5 + 0.3 * sum(len(x.split()) for x in hook)
            exit_at = min(max(1.6, hold), segs[0]["dur"] - 0.3)
            js.append(f'tl.to("#sc-hook-wrap", {{ x: -260, opacity: 0, filter: "blur(16px)", duration: 0.2, ease: "power3.in" }}, {_r(exit_at)});')
            overlays.append(("sc-hook", 0.0, _r(exit_at + 0.27), '<div id="sc-hook-wrap" class="fx-stack" style="top:320px">' + "".join(parts) + "</div>", js))
            cue("whoosh", "whoosh.mp3", exit_at + 0.1, lv["whoosh"])
        first = segs[0]
        drop_at = first["start"] + (first.get("payoff") or 0.5)

    outro = texts.get("outro") or []
    if outro:
        start = total - 2.2
        top, main = (outro[0], outro[1]) if len(outro) == 2 else (None, outro[0])
        parts, js = [], []
        if top:
            parts.append(f'<div id="sc-outro-top" class="fx-display" style="font-size:{_fit(top, 96)}px" data-var-text="outro_top">{_t(top)}</div>')
            js.append(f'tl.fromTo("#sc-outro-top", {{ opacity: 0, filter: "blur(10px)", scale: 1.15 }}, {{ opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.18, ease: "power4.out" }}, {_r(start + 0.01)});')
        parts.append(f'<div id="sc-outro-main" class="fx-display fx-accent" style="font-size:{_fit(main, 100)}px" data-var-text="outro_main">{_t(main)}</div>')
        js.append(f'tl.fromTo("#sc-outro-main", {{ opacity: 0, filter: "blur(10px)", scale: 1.6 }}, {{ opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.24, ease: "expo.out" }}, {_r(start + 0.13)});')
        top_px = 620 if fmt == "ranking" else 300
        overlays.append(("sc-outro", _r(start), 2.2, f'<div id="sc-outro-wrap" class="fx-stack" style="top:{top_px}px">' + "".join(parts) + "</div>", js))
        marks["outro"] = _r(start + 0.6)

    # ---- music: one bed, drop on #1 (ranking) or the first payoff (montage)
    music_tag = ""
    if music:
        drop, why = media.pick_drop(music, drop_at, total)
        ms = max(0.0, drop - drop_at)
        log.append(f"music: {why}; enters at {ms:.2f}s, drop at {drop_at:.2f}s")
        shutil.copy2(music, d / "assets" / ("music" + music.suffix))
        lane = {"version": 1, "lanes": [{"target": "volume", "points": [
            {"t": 0, "v": 0.85}, {"t": _r(max(0.0, drop_at - 0.6)), "v": 0.85}, {"t": _r(max(0.0, drop_at - 0.3)), "v": 0.5},
            {"t": _r(drop_at), "v": 1.15}, {"t": _r(total - 1.0), "v": 1.15}]}]}
        music_tag = (f'<audio id="music" class="clip" src="assets/music{music.suffix}" data-start="0" data-duration="{total}" '
                     f'data-media-start="{_r(ms)}" data-track-index="20" data-volume="{lv["music"]}" data-fade-out="0.7" '
                     f"data-automation='{_attr_json(lane)}'></audio>")

    # ---- files
    vids = "\n".join(f'      <video id="seg-{i + 1}" class="clip seg" src="assets/{s["file"]}" playsinline data-has-audio="true" '
                     f'data-start="{s["start"]}" data-duration="{s["dur"]}" data-track-index="{i % 2}" data-volume="1"></video>'
                     for i, s in enumerate(segs))
    auds = "\n".join(f'      <audio id="{c["id"]}" class="clip" src="assets/sfx/{c["file"]}" data-start="{c["start"]}" data-duration="{c["dur"]}"'
                     + (f' data-media-start="{c["ms"]}"' if c["ms"] else "") + f' data-track-index="{TRACK[c["id"].split("-")[1]]}" data-volume="{c["vol"]}"'
                     + (f' data-fade-out="{c["fade"]}"' if c["fade"] else "") + "></audio>" for i, c in enumerate(cues))
    (d / "index.html").write_text(f"""<!doctype html>
<html lang="en" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>{CSS}    </style>
  </head>
  <body>
    <!-- generated by hypeedit.shortcompose ({fmt}); rebuild overwrites this file -->
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1080" data-height="1920">
{vids}
      <div id="fx" data-composition-id="fx" data-composition-src="compositions/fx.html" data-start="0" data-duration="{total}" data-track-index="5" data-track-kind="graphics" data-width="1080" data-height="1920" style="z-index: 5"></div>
      {music_tag}
{auds}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
""")
    variables = json.dumps([{"id": "header", "type": "string", "label": "Header", "default": texts.get("header") or ""},
                            {"id": "accent", "type": "color", "label": "Accent", "default": accent}])
    els = "\n".join(f'        <div id="{oid}" class="clip fx-full" data-start="{_r(st)}" data-duration="{_r(du)}" data-track-index="{i}" '
                    f'data-layout-allow-overflow data-layout-allow-overlap>\n          {h}\n        </div>'
                    for i, (oid, st, du, h, _) in enumerate(overlays))
    js = "\n".join("          " + line for *_, lines in overlays for line in lines)
    (d / "compositions" / "fx.html").write_text(f"""<html data-composition-variables='{variables.replace("'", "&#39;")}'>
  <body>
    <template>
      <style>{FX_CSS % {"accent": accent}}      </style>
      <div id="root" data-composition-id="fx" data-width="1080" data-height="1920">
{els}
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
{js}
          window.__timelines["fx"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
""")
    (d / "short_map.json").write_text(json.dumps({"format": fmt, "duration": total, "marks": marks,
                                                  "segments": [{k: v for k, v in s.items() if k != "path"} for s in segs],
                                                  "log": log}, indent=1))
    return {"duration": total, "marks": marks, "log": log}
