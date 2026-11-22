"""hypeedit CLI.

  python3 -m hypeedit prep   RAW OUT.mp4 [--audio game.wav]      fast proxy, then 1080x1920 master
  python3 -m hypeedit look   SOURCE.mp4 OUT_DIR [--detail A,B ...] sheets to find beats
  python3 -m hypeedit build  PLAN.json                            plan -> HyperFrames project + check
  python3 -m hypeedit snap   PLAN.json                            frames at every mark -> contact sheet
  python3 -m hypeedit render PLAN.json [--draft] [-o OUT.mp4]     master render + loudness (--draft: proxy)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import media, moves, plan as plan_mod, project, style, timing


def cmd_prep(a):
    info = media.prep(a.raw, a.out, audio=a.audio, trim_top=a.trim_top, trim_bottom=a.trim_bottom,
                      x_offset=a.x_offset, sharpen=a.sharpen, master=not a.proxy_only)
    print(f"proxy  {info['proxy']} (540x960, for look/build/preview)")
    if info["master"]:
        print(f"master {info['master']} (1080x1920, used by render)")
    print(f"crop {info['crop_width']}px wide from {info['crop_from']}, {info['fps']} fps")
    if info["crop_width"] < 600:
        print("note: crop under 600 px wide is upscaled about 2x and will look soft; re-fetch the raw at 1440p "
              "(raise download.max_height in the job, then `python3 -m pipeline run`) for a 697 px crop")


def cmd_look(a):
    detail = [tuple(float(x) for x in d.split(",")) for d in a.detail or []]
    for p in media.look(a.source, a.out_dir, detail):
        print(p)
    print("grid cells in detail sheets are 108x192 output px (10x10 over the 1080x1920 frame)")


def _compose(path):
    src_dur = None
    raw = json.loads(pathlib.Path(path).read_text())
    if raw.get("source"):
        sp = pathlib.Path(path).resolve().parent / raw["source"]
        for cand in (sp, plan_mod.proxy_of(sp)):
            if cand.exists():
                src_dur = media.probe(cand)["duration"]
                break
    p = plan_mod.load(path, src_dur)
    st = style.get(p.style)
    tm, segs, win = timing.build(p, src_dur, st)
    music_start = None
    if p.music:
        P = tm.out(p.payoff.t)
        if p.music_drop is not None:
            drop, why = p.music_drop, f"drop {p.music_drop}s (from plan)"
        else:
            drop, why = media.pick_drop(p.music, P, tm.duration)
        music_start = max(0.0, drop - P)
        print(f"music: {why}; enters at {music_start:.2f}s")
    e = moves.compose(p, tm, win, st, music_start)
    rows = [{"kind": b.kind, "source": b.t, "output": tm.out(b.t), **({"end_output": tm.out(b.end)} if b.end else {})} for b in p.beats]
    return p, st, tm, e, rows


def cmd_build(a):
    p, st, tm, e, rows = _compose(a.plan)
    print(f"{'beat':8} {'source':>7} {'output':>7}")
    for r in rows:
        span = f"-{r['end_output']:.2f}" if "end_output" in r else ""
        print(f"{r['kind']:8} {r['source']:7.2f} {r['output']:7.2f}{span}")
    for line in e.log:
        print(line)
    d = project.write(p, e, tm.lane(), rows)
    ok, found = project.check(d)
    for sev, code, msg in found:
        print(f"  {sev}: {code}: {msg}")
    print(f"project: {d}\ncheck: {'ok' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


def _project(path):
    p = plan_mod.load(path)
    m = json.loads((p.out_dir / "edit_map.json").read_text())
    return p, m


def cmd_snap(a):
    p, m = _project(a.plan)
    marks = m["marks"]
    times = sorted({0.0, *(round(v, 3) for v in marks.values()), round(marks["payoff"] - 0.3, 3), round(marks["payoff"] + 0.05, 3)})
    times = [t for t in times if 0 <= t < m["duration"]]
    out = p.out_dir / ".hypeedit" / "snap"
    res = media.npx_json(["snapshot", "--at", ",".join(map(str, times)), "--no-end", "-o", str(out), "--json"], cwd=p.out_dir)
    for s in res.get("contactSheets", []):
        print(s)


def cmd_render(a):
    p, m = _project(a.plan)
    d = p.out_dir
    if a.draft:
        media_file, quality, fps = p.preview_media, "draft", "15"
        out = pathlib.Path(a.output or d.parent / f"{p.name}_draft.mp4").resolve()
    else:
        if not p.source.exists():
            raise SystemExit(f"master {p.source} is not there yet (prep still encoding?); use --draft for a proxy render")
        media_file, quality, fps = p.source, "delivery", "30"
        out = pathlib.Path(a.output or d.parent / f"{p.name}_fx.mp4").resolve()
    project.sync(media_file, d / "assets" / media_file.name)
    before = project.point_video(d, media_file.name)
    try:
        media.run(["npx", "hyperframes", "render", "--fps", fps, "--quality", quality, "-o", str(out)], cwd=d, capture=False)
    finally:
        project.point_video(d, before)  # the preview goes back to the proxy
    print(f"rendered {out} from {media_file.name} ({quality})")
    if a.draft:
        return
    dd = media.npx_json(["audio", str(out), "--json"])
    loud = dd["items"][0]["loudness"]
    lufs = loud["lufsIntegrated"]
    print(f"loudness {lufs} LUFS, true peak {loud['truePeakDb']} dB, clipping {loud['clipping']['count']}")
    if not -16 <= lufs <= -13:
        print(f"mix is off target (-16..-13): set \"mix_gain_db\": {round(p.mix_gain_db + (-14.5 - lufs), 1)} in the plan, build, render")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hypeedit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("prep", help="raw footage -> clean 1080x1920 source")
    s.add_argument("raw")
    s.add_argument("out")
    s.add_argument("--audio", help="replacement audio (e.g. demucs no_vocals.wav)")
    s.add_argument("--trim-top", type=float, default=0.04)
    s.add_argument("--trim-bottom", type=float, default=0.10)
    s.add_argument("--x-offset", type=float, default=0.0)
    s.add_argument("--sharpen", type=float, default=0.6)
    s.add_argument("--proxy-only", action="store_true", help="only the fast 540x960 proxy; run again without it for the master")
    s.set_defaults(fn=cmd_prep)

    s = sub.add_parser("look", help="contact sheets + audio envelope for finding beats")
    s.add_argument("source")
    s.add_argument("out_dir")
    s.add_argument("--detail", action="append", metavar="A,B", help="10 fps strip with focus grid, source seconds")
    s.set_defaults(fn=cmd_look)

    for name, fn, h in (("build", cmd_build, "plan -> HyperFrames project, then check"),
                        ("snap", cmd_snap, "snapshot every mark of a built plan"),
                        ("render", cmd_render, "render a built plan and measure loudness")):
        s = sub.add_parser(name, help=h)
        s.add_argument("plan")
        if name == "render":
            s.add_argument("-o", "--output")
            s.add_argument("--draft", action="store_true", help="fast low-quality render from the proxy, for watching")
        s.set_defaults(fn=fn)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except plan_mod.PlanError as exc:
        raise SystemExit(f"plan invalid: {exc}")


if __name__ == "__main__":
    main()
