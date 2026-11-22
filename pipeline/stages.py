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


def plain_done(job: Job, c: Clip) -> bool:
    return job.plain(c).exists() and job.raw_is_current(c)


def plain_cuts(job: Job, clips: list[Clip], force=False) -> list[int]:
    """Run the clipper for clips whose plain cut or raw download is missing or stale. Returns failed ids."""
    todo = [c for c in clips if force or not plain_done(job, c)]
    if not todo:
        return []
    job.ws.mkdir(parents=True, exist_ok=True)
    resolved = dict(job.cfg)
    resolved["output_dir"] = str(job.plain_dir)
    rp = job.ws / "job.resolved.json"
    rp.write_text(json.dumps(resolved, indent=2, default=str))
    # a short that exists over a stale (lower-res) raw is re-made: --force for those
    stale = [c.id for c in todo if force or job.plain(c).exists()]
    fresh = [c.id for c in todo if c.id not in stale]
    failed = []
    for ids, extra in ((fresh, []), (stale, ["--force"])):
        if not ids:
            continue
        res = sh([python(), "-m", "pipeline.clipper", "--config", rp, "--clips", *ids, "--keep-temp", *extra])
        if res.returncode != 0:
            failed += [i for i in ids if not job.plain(next(c for c in clips if c.id == i)).exists()]
    return failed


# ------------------------------------------------------------------ edit source


def _prep(job: Job, c: Clip, master: bool):
    crop = job.cfg["crop"]
    job.edit_dir(c).mkdir(parents=True, exist_ok=True)
    audio, warn = job.edit_audio(c)
    if warn:
        print(f"  WARNING {warn}")
    info = hmedia.prep(job.raw(c), job.master(c), audio=audio, trim_top=crop.get("trim_top", 0.04),
                       trim_bottom=crop.get("trim_bottom", 0.10), x_offset=crop.get("x_offset", 0.0), master=master,
                       mute=c.audio == "muted")
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


def _secs(v) -> float:
    sec = 0.0
    for part in str(v).split(":"):
        sec = sec * 60 + float(part)
    return sec


def _hint_context(c: Clip) -> dict:
    """What research knew about the moment, with the payoff in clip (source.mp4) seconds."""
    h = c.hint or {}
    out = {k: h[k] for k in ("kind", "hook", "why") if h.get(k)}
    if h.get("payoff"):
        out["payoff_hint_t"] = round(_secs(h["payoff"]) - _secs(c.start), 2)
        out["payoff_hint_note"] = "research's estimate in source.mp4 seconds: start the frame search here"
    out["audio_source"] = c.audio
    return out


def draft(job: Job, c: Clip) -> None:
    """Template the AI/editor turns into plan.json (see .claude/skills/hype-edit)."""
    if job.plan(c).exists() or job.draft(c).exists():
        return
    music = os.path.relpath(job.edit["music"], job.edit_dir(c)) if job.edit["music"] else None
    sh_ = job.short_of(c)
    segment = c.mode == "segment"
    hint = _hint_context(c)
    beats = []
    if "payoff_hint_t" in hint:
        beats.append({"kind": "payoff", "t": hint["payoff_hint_t"], "focus": [540, 960],
                      "note": "prefilled from research: pin t and focus on the look sheets before keeping it"})
    text = {"stamp": "<1-2 WORDS, or empty for none>", "accent": job.edit["accent"]}
    if not segment:
        text.update(hook=["<LINE 1>", "<ACCENT LINE>"], tease=None, outro=["<LINE 1>", "<QUESTION?>"])
    tpl = {
        "name": c.key,
        "source": "source.mp4",
        "music": {"file": music} if music and not segment else None,
        "style": c.style,
        "mode": c.mode,
        "out_dir": "project",
        "text": text,
        "beats": beats,
        "_context": {
            "label": c.label, "title": c.title, "caption": c.caption,
            "stream_range": f"{c.start}-{c.end}",
            **hint,
            "short": ({"key": sh_.key, "format": sh_.format, "position": sh_.clips.index(c) + 1, "of": len(sh_.clips)}
                      if sh_ else None),
            "mode_note": ("segment of a multi-clip short: no hook, outro or music here; the short adds them"
                          if segment else "a whole short: hook at frame 0, outro question, music"),
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
    out = job.clip_render(c)
    return out.exists() and not newer(em, out) and not newer(job.master(c), out)


def render(job: Job, c: Clip, draft_only=False) -> tuple[bool, str]:
    """A clip's edit -> renders/ (a whole short, or a segment of one)."""
    out = job.clip_render(c)
    if draft_only:
        out = out.with_name(out.stem + "_draft.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "hypeedit", "render", job.plan(c), "-o", out] + (["--draft"] if draft_only else [])
    res = sh(cmd, quiet=True)
    text = (res.stdout or "") + (res.stderr or "")
    if res.returncode != 0:
        return False, text.strip()[-1500:]
    lines = [ln for ln in text.splitlines() if ln.startswith(("rendered", "loudness", "mix is"))]
    return True, "\n".join(lines)


# ------------------------------------------------------------------ shorts


def _short_meta(job: Job, s) -> str:
    first = s.clips[0]
    title = s.title or first.title
    caption = s.caption or first.caption
    raw = next((x for x in job.cfg["clips"] if x["id"] == first.id), {})
    tags = s.hashtags or raw.get("hashtags") or job.cfg.get("default_hashtags", "#Shorts")
    return f"TITLE:\n{title}\n\nCAPTION:\n{caption}\n\nHASHTAGS:\n{tags}\n"


def short_inputs(job: Job, s) -> list:
    """What a short is made from; it is out of date when any of these is newer."""
    if s.format == "single":
        c = s.clips[0]
        return [job.clip_render(c) if c.edit else job.plain(c)]
    return [job.clip_render(c) for c in s.clips]


def short_ready(job: Job, s) -> bool:
    return all(p.exists() for p in short_inputs(job, s))


def short_done(job: Job, s) -> bool:
    out = job.final_short(s)
    return out.exists() and not any(newer(p, out) for p in short_inputs(job, s))


def make_short(job: Job, s) -> tuple[bool, str]:
    """single: the clip's render is the short. montage/ranking: compose the segments, render."""
    job.final.mkdir(parents=True, exist_ok=True)
    out = job.final_short(s)
    if s.format == "single":
        shutil.copy2(short_inputs(job, s)[0], out)
        text = "single: " + _rel_name(short_inputs(job, s)[0])
    else:
        from hypeedit import shortcompose

        segs = []
        for i, c in enumerate(s.clips):
            payoff = None
            em = job.project(c) / "edit_map.json"
            if em.exists():
                payoff = json.loads(em.read_text())["marks"].get("payoff")
            segs.append({"path": job.clip_render(c), "payoff": payoff,
                         "rank": (len(s.clips) - i) if s.format == "ranking" else None})
        texts = {"header": s.header, "hook": s.hook, "outro": s.outro}
        info = shortcompose.build(job.compose_dir(s), s.format, segs, texts, job.edit["music"], job.edit["accent"])
        check = subprocess.run(["npx", "hyperframes", "check", "--json"], cwd=job.compose_dir(s), capture_output=True, text=True)
        if '"ok":false' in check.stdout.replace(" ", ""):
            return False, "compose check failed: " + check.stdout[-800:]
        res = subprocess.run(["npx", "hyperframes", "render", "--fps", "30", "--quality", "delivery", "-o", str(out)],
                             cwd=job.compose_dir(s), capture_output=True, text=True, env=env())
        if res.returncode != 0 or not out.exists():
            return False, ((res.stdout or "") + (res.stderr or ""))[-1500:]
        text = f"{s.format}: {len(segs)} segments, {info['duration']:.1f}s; " + "; ".join(info["log"])
    (job.final / f"{s.key}.txt").write_text(_short_meta(job, s), encoding="utf-8")
    loud = hmedia.npx_json(["audio", str(out), "--json"])["items"][0]["loudness"]
    return True, f"{text}\nloudness {loud['lufsIntegrated']} LUFS, true peak {loud['truePeakDb']} dB"


def _rel_name(p) -> str:
    return pathlib.Path(p).name
