"""Pipeline stages. Each one checks its own outputs, so `run` is safe to repeat:
it does only what is missing or out of date.

    short   clipper: download (max_height), crop, demucs game audio, plain short
    proxy   540x960 edit source            (hypeedit prep --proxy-only)
    look    overview sheet + audio envelope (hypeedit look)
    draft   plan.draft.json template for the AI/editor
    master  1080x1920 edit source          (hypeedit prep)
    build   plan.json -> HyperFrames project + check + snap sheet
    render  master render -> final/ (+ post metadata .txt)
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from hypeedit import media as hmedia

from .job import ROOT, Clip, Job

VENV_BIN = ROOT / ".venv" / "bin"


def env() -> dict:
    e = dict(os.environ)
    if VENV_BIN.exists():
        e["PATH"] = f"{VENV_BIN}{os.pathsep}{e.get('PATH', '')}"
    return e


def python() -> str:
    p = VENV_BIN / "python"
    return str(p) if p.exists() else sys.executable


def sh(cmd: list[str], quiet=False) -> subprocess.CompletedProcess:
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    res = subprocess.run([str(c) for c in cmd], cwd=ROOT, env=env(), text=True,
                         capture_output=quiet)
    return res


def newer(a: pathlib.Path, b: pathlib.Path) -> bool:
    """a exists and is newer than b (or b is missing)."""
    return a.exists() and (not b.exists() or a.stat().st_mtime > b.stat().st_mtime)


# ------------------------------------------------------------------ short


def short_done(job: Job, c: Clip) -> bool:
    return job.short(c).exists() and job.raw_is_current(c)


def shorts(job: Job, clips: list[Clip], force=False) -> list[int]:
    """Run the clipper for clips whose short or raw download is missing or stale. Returns failed ids."""
    todo = [c for c in clips if force or not short_done(job, c)]
    if not todo:
        return []
    job.ws.mkdir(parents=True, exist_ok=True)
    resolved = dict(job.cfg)
    resolved["output_dir"] = str(job.shorts)
    rp = job.ws / "job.resolved.json"
    rp.write_text(json.dumps(resolved, indent=2, default=str))
    # a short that exists over a stale (lower-res) raw is re-made: --force for those
    stale = [c.id for c in todo if force or job.short(c).exists()]
    fresh = [c.id for c in todo if c.id not in stale]
    failed = []
    for ids, extra in ((fresh, []), (stale, ["--force"])):
        if not ids:
            continue
        res = sh([python(), "-m", "pipeline.clipper", "--config", rp, "--clips", *ids, "--keep-temp", *extra])
        if res.returncode != 0:
            failed += [i for i in ids if not job.short(next(c for c in clips if c.id == i)).exists()]
    return failed


# ------------------------------------------------------------------ edit source


def _prep(job: Job, c: Clip, master: bool):
    crop = job.cfg["crop"]
    job.edit_dir(c).mkdir(parents=True, exist_ok=True)
    info = hmedia.prep(job.raw(c), job.master(c), audio=job.game_audio(c), trim_top=crop.get("trim_top", 0.04),
                       trim_bottom=crop.get("trim_bottom", 0.10), x_offset=crop.get("x_offset", 0.0), master=master)
    return info


def proxy(job: Job, c: Clip) -> str | None:
    if not job.raw(c).exists():
        return "no raw download"
    if newer(job.raw(c), job.proxy(c)):
        print(f"  proxy {c.key}", flush=True)
        info = _prep(job, c, master=False)
        if info["crop_width"] < 600:
            print(f"  note: {c.key} crop is {info['crop_width']} px wide; the master will look soft")
    return None


def master(job: Job, c: Clip) -> None:
    if job.raw(c).exists() and newer(job.raw(c), job.master(c)):
        print(f"  master {c.key} (slow encode)", flush=True)
        _prep(job, c, master=True)


def look(job: Job, c: Clip, detail: list[tuple[float, float]] | None = None) -> list[str]:
    ov = job.look_dir(c) / "overview.jpg"
    if detail or newer(job.proxy(c), ov):
        return hmedia.look(job.proxy(c), job.look_dir(c), detail)
    return []


def draft(job: Job, c: Clip) -> None:
    """Template the AI/editor turns into plan.json (see .claude/skills/hype-edit)."""
    if job.plan(c).exists() or job.draft(c).exists():
        return
    music = os.path.relpath(job.edit["music"], job.edit_dir(c)) if job.edit["music"] else None
    tpl = {
        "name": c.key,
        "source": "source.mp4",
        "music": {"file": music} if music else None,
        "style": job.edit["style"],
        "out_dir": "project",
        "text": {"hook": ["<LINE 1>", "<ACCENT LINE>"], "tease": None, "stamp": "<1-2 WORDS>",
                 "outro": ["<LINE 1>", "<QUESTION?>"], "accent": job.edit["accent"]},
        "beats": [],
        "_context": {
            "label": c.label, "title": c.title, "caption": c.caption,
            "stream_range": f"{c.start}-{c.end}",
            "look": ["look/overview.jpg", "look/audio_envelope.txt"],
            "detail": f"python3 -m pipeline look {job.path.relative_to(ROOT)} --clip {c.id} --detail A,B",
            "save_as": "plan.json",
        },
    }
    job.draft(c).write_text(json.dumps(tpl, indent=2) + "\n")


# ------------------------------------------------------------------ build / render


def build_done(job: Job, c: Clip) -> bool:
    em = job.project(c) / "edit_map.json"
    return em.exists() and not newer(job.plan(c), em) and not newer(job.proxy(c), em)


def build(job: Job, c: Clip) -> tuple[bool, str]:
    res = sh([sys.executable, "-m", "hypeedit", "build", job.plan(c)], quiet=True)
    out = (res.stdout or "") + (res.stderr or "")
    if res.returncode != 0:
        return False, out.strip()[-1500:]
    snap = sh([sys.executable, "-m", "hypeedit", "snap", job.plan(c)], quiet=True)
    if snap.returncode != 0:
        return True, out.strip() + "\n(snap failed: " + (snap.stderr or "")[-300:] + ")"
    return True, out.strip()


def render_done(job: Job, c: Clip) -> bool:
    em = job.project(c) / "edit_map.json"
    return job.final_video(c).exists() and not newer(em, job.final_video(c)) and not newer(job.master(c), job.final_video(c))


def render(job: Job, c: Clip, draft_only=False) -> tuple[bool, str]:
    job.final.mkdir(parents=True, exist_ok=True)
    out = job.final / (f"{c.key}_draft.mp4" if draft_only else f"{c.key}.mp4")
    cmd = [sys.executable, "-m", "hypeedit", "render", job.plan(c), "-o", out] + (["--draft"] if draft_only else [])
    res = sh(cmd, quiet=True)
    text = (res.stdout or "") + (res.stderr or "")
    if res.returncode != 0:
        return False, text.strip()[-1500:]
    if job.meta(c).exists():
        shutil.copy2(job.meta(c), job.final / f"{c.key}.txt")
    lines = [ln for ln in text.splitlines() if ln.startswith(("rendered", "loudness", "mix is"))]
    return True, "\n".join(lines)
