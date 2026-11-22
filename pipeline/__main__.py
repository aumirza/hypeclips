"""Clips pipeline: one job config in, hype-edited shorts out.

  python3 -m pipeline doctor                         tools and versions
  python3 -m pipeline run    jobs/<job>.json         everything up to review (resumable)
  python3 -m pipeline status jobs/<job>.json         where every clip stands, and what is next
  python3 -m pipeline look   jobs/<job>.json --clip N --detail A,B [--detail C,D]
  python3 -m pipeline render jobs/<job>.json [--draft]

Options for run/status/render: --clips 1 3 7 limits to those ids.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from . import stages
from .job import ROOT, Job


def _rel(p) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def status_rows(job: Job, clips):
    rows = []
    for c in clips:
        r = {"clip": c.key, "short": "done" if stages.short_done(job, c) else ("stale" if job.short(c).exists() else "-")}
        if not c.edit:
            r.update(proxy="off", look="off", plan="off", master="off", build="off", render="off")
            rows.append((c, r))
            continue
        r["proxy"] = "done" if job.proxy(c).exists() else "-"
        r["look"] = "done" if (job.look_dir(c) / "overview.jpg").exists() else "-"
        r["plan"] = "done" if job.plan(c).exists() else ("draft" if job.draft(c).exists() else "-")
        r["master"] = "done" if job.master(c).exists() else "-"
        r["build"] = "done" if stages.build_done(job, c) else ("stale" if (job.project(c) / "edit_map.json").exists() else "-")
        r["render"] = "done" if stages.render_done(job, c) else ("stale" if job.final_video(c).exists() else "-")
        rows.append((c, r))
    return rows


def print_status(job: Job, clips):
    rows = status_rows(job, clips)
    cols = ["clip", "short", "proxy", "look", "plan", "master", "build", "render"]
    w = max(len(r["clip"]) for _, r in rows) + 2
    print("\n" + "clip".ljust(w) + "".join(c.ljust(8) for c in cols[1:]))
    for _, r in rows:
        print(r["clip"].ljust(w) + "".join(r[c].ljust(8) for c in cols[1:]))
    nxt = []
    for c, r in rows:
        if r["plan"] == "off":
            continue
        if r["short"] != "done":
            why = "below download.max_height" if r["short"] == "stale" else "missing"
            nxt.append(f"{c.key}: short {why} -> `run` (re)downloads and re-makes it")
        elif r["plan"] != "done":
            nxt.append(f"{c.key}: NEEDS PLAN -> read {_rel(job.look_dir(c))}/, fill {_rel(job.draft(c))}, save as plan.json")
        elif r["build"] != "done":
            nxt.append(f"{c.key}: plan ready -> `run` builds it")
        elif r["render"] != "done":
            sheets = job.snap_sheets(c)
            nxt.append(f"{c.key}: REVIEW {', '.join(_rel(s) for s in sheets) or '(no snap sheet)'} -> fix plan.json and `run`, or `render`")
    print("\nnext:" if nxt else "\nall selected clips are rendered: " + _rel(job.final))
    for n in nxt:
        print("  - " + n)


def cmd_run(a):
    job = Job(a.job)
    clips = job.select(a.clips)
    print(f"job {job.name}: {len(clips)} clips -> {_rel(job.ws)}")

    print("\n[short] download + crop + game audio + plain short")
    failed = stages.shorts(job, clips, force=a.force_shorts)
    for i in failed:
        print(f"  FAILED clip {i}")
    edit = [c for c in clips if c.edit and job.raw(c).exists()]

    print("\n[proxy, look, draft] edit sources and sheets for finding beats")
    for c in edit:
        err = stages.proxy(job, c)
        if err:
            print(f"  {c.key}: {err}")
            continue
        stages.look(job, c)
        stages.draft(job, c)

    if not a.no_master:
        print("\n[master] full-quality edit sources")
        for c in edit:
            stages.master(job, c)

    print("\n[build] plans -> HyperFrames projects, check, snap")
    for c in edit:
        if not job.plan(c).exists():
            continue
        if stages.build_done(job, c):
            print(f"  {c.key}: up to date")
            continue
        ok, out = stages.build(job, c)
        print(f"  {c.key}: {'built' if ok else 'BUILD FAILED'}")
        print("    " + out.replace("\n", "\n    "))

    print_status(job, clips)


def cmd_status(a):
    job = Job(a.job)
    print_status(job, job.select(a.clips))


def cmd_render(a):
    job = Job(a.job)
    clips = [c for c in job.select(a.clips) if c.edit]
    for c in clips:
        if not stages.build_done(job, c):
            print(f"{c.key}: not built (or plan changed since build); `run` first")
            continue
        if not a.draft and not a.force and stages.render_done(job, c):
            print(f"{c.key}: up to date ({_rel(job.final_video(c))})")
            continue
        if not a.draft and not job.master(c).exists():
            print(f"{c.key}: master missing; `run` without --no-master first")
            continue
        print(f"{c.key}: rendering {'draft' if a.draft else 'master'} ...", flush=True)
        ok, out = stages.render(job, c, draft_only=a.draft)
        print("  " + out.replace("\n", "\n  ") if ok else f"  RENDER FAILED\n  {out}")
    print_status(job, job.select(a.clips))


def cmd_look(a):
    job = Job(a.job)
    c = job.select([a.clip])[0]
    detail = [tuple(float(x) for x in d.split(",")) for d in a.detail or []]
    if not job.proxy(c).exists():
        raise SystemExit(f"{c.key}: no proxy yet; `run` first")
    for p in stages.look(job, c, detail):
        print(_rel(__import__("pathlib").Path(p)))
    print("grid cells in detail sheets are 108x192 output px (10x10 over the 1080x1920 frame)")


def cmd_doctor(a):
    ok = True
    venv_ytdlp = stages.VENV_BIN / "yt-dlp"
    checks = [
        ("ffmpeg", shutil.which("ffmpeg")),
        ("ffprobe", shutil.which("ffprobe")),
        ("node/npx", shutil.which("npx")),
        ("yt-dlp", str(venv_ytdlp) if venv_ytdlp.exists() else shutil.which("yt-dlp")),
        ("demucs", str(stages.VENV_BIN / "demucs") if (stages.VENV_BIN / "demucs").exists() else shutil.which("demucs")),
    ]
    for name, where in checks:
        print(f"  {'ok ' if where else 'MISSING'} {name:9} {where or ''}")
        ok &= bool(where) or name == "demucs"
    try:
        v = subprocess.run(["npx", "hyperframes", "--version"], capture_output=True, text=True, cwd=ROOT).stdout.strip().splitlines()[-1]
        print(f"  ok  hyperframes {v}")
    except Exception:
        print("  MISSING hyperframes (npx hyperframes)")
        ok = False
    if not (stages.VENV_BIN / "demucs").exists():
        print("  note: without demucs the clipper falls back to ffmpeg vocal cut (worse game audio)")
    sys.exit(0 if ok else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("doctor", help="check tools")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("run", help="everything up to review; safe to repeat")
    s.add_argument("job")
    s.add_argument("--clips", type=int, nargs="+")
    s.add_argument("--no-master", action="store_true", help="skip the slow master encodes for now")
    s.add_argument("--force-shorts", action="store_true", help="re-download and re-make plain shorts")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("status", help="stage table and next actions")
    s.add_argument("job")
    s.add_argument("--clips", type=int, nargs="+")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("render", help="render built clips to workspace/<job>/final")
    s.add_argument("job")
    s.add_argument("--clips", type=int, nargs="+")
    s.add_argument("--draft", action="store_true", help="fast 15 fps render from the proxy")
    s.add_argument("--force", action="store_true", help="render even if up to date")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("look", help="detail sheets for one clip")
    s.add_argument("job")
    s.add_argument("--clip", type=int, required=True)
    s.add_argument("--detail", action="append", metavar="A,B", help="source seconds; 10 fps strip with focus grid")
    s.set_defaults(fn=cmd_look)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
