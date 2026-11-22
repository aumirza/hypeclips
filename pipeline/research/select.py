"""Picks -> shortlist (fit, snap, dedupe, rank, variety) -> verify sheets -> selection -> job clips."""

from __future__ import annotations

import concurrent.futures as cf
import json
import math
import pathlib
import re
import subprocess

from . import fetch
from .windows import hms


def parse_t(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    sec = 0.0
    for part in str(v).strip().split(":"):
        sec = sec * 60 + float(part)
    return sec


def hmsf(s: float) -> str:
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}"


def load_picks(picks_dir: pathlib.Path, kinds: dict, duration: float) -> tuple[list[dict], list[str]]:
    cands, problems = [], []
    for p in sorted(picks_dir.glob("w*.json")):
        try:
            items = json.loads(p.read_text())
        except Exception as e:
            problems.append(f"{p.name}: not valid JSON ({e})")
            continue
        for i, c in enumerate(items):
            try:
                c["_s"], c["_e"] = parse_t(c["start"]), parse_t(c["end"])
                c["score"] = float(c["score"])
            except Exception as e:
                problems.append(f"{p.name}[{i}]: needs start, end, score ({e})")
                continue
            if c.get("kind") not in kinds:
                problems.append(f"{p.name}[{i}]: kind {c.get('kind')!r} is not one of {sorted(kinds)}")
                continue
            if not (0 <= c["_s"] < c["_e"] <= duration + 1):
                problems.append(f"{p.name}[{i}]: times outside the stream")
                continue
            c["_p"] = parse_t(c["payoff"]) if c.get("payoff") is not None else None
            c["window"] = p.stem
            cands.append(c)
    return cands, problems


def fit(c: dict, kind: dict, lines: list[dict]) -> None:
    lo, hi = kind["length"]
    s, e, p = c["_s"], c["_e"], c["_p"]
    if e - s > hi:
        if p is not None and s <= p <= e:
            s = max(s, p - 0.55 * hi)
            e = s + hi
        else:
            e = s + hi
    if e - s < lo:
        mid = p if p is not None else (s + e) / 2
        s = max(0.0, mid - lo / 2)
        e = s + lo
    if kind.get("audio") == "original" and lines:
        # talk-driven clips: start and end on sentence edges (never mid-word)
        starts = [ln["start"] for ln in lines if ln["start"] <= s + 0.5]
        ends = [ln["end"] for ln in lines if ln["end"] >= e - 0.5]
        s2, e2 = (max(starts) if starts else s), (min(ends) if ends else e)
        if lo <= e2 - s2 <= hi + 3:
            s, e = s2 - 0.25, e2 + 0.4
    c["_s"], c["_e"] = round(max(0.0, s), 2), round(e, 2)


def shortlist(cands: list[dict], r: dict, lines: list[dict]) -> list[dict]:
    kinds = r["kinds"]
    for c in cands:
        fit(c, kinds[c["kind"]], lines)
    kept, per_kind = [], {}
    size = max(int(r["count"]) + 3, math.ceil(int(r["count"]) * 1.5))
    for c in sorted(cands, key=lambda c: -c["score"]):
        if c["score"] < float(r["min_score"]):
            continue
        if any(not (c["_e"] + 10 < o["_s"] or c["_s"] > o["_e"] + 10) for o in kept):
            continue
        cap = r.get("max_per_kind")
        if cap and per_kind.get(c["kind"], 0) >= cap:
            continue
        kept.append(c)
        per_kind[c["kind"]] = per_kind.get(c["kind"], 0) + 1
        if len(kept) >= size:
            break
    out = []
    for i, c in enumerate(sorted(kept, key=lambda c: -c["score"]), 1):
        out.append({"id": f"s{i:02d}", "start": hmsf(c["_s"]), "end": hmsf(c["_e"]), "length": round(c["_e"] - c["_s"], 1),
                    "kind": c["kind"], "score": c["score"], "payoff": hmsf(c["_p"]) if c["_p"] is not None else None,
                    "hook": c.get("hook", ""), "title": c.get("title", ""), "caption": c.get("caption", ""),
                    "hashtags": c.get("hashtags", []), "why": c.get("why", ""), "window": c["window"]})
    return out


def verify_sheets(items: list[dict], url: str, vdir: pathlib.Path, cookies: list[str]) -> None:
    vdir.mkdir(parents=True, exist_ok=True)

    def one(it):
        s, e = parse_t(it["start"]), parse_t(it["end"])
        piece = vdir / f"{it['id']}.mp4"
        sheet = vdir / f"{it['id']}.jpg"
        if sheet.exists():
            it["sheet"] = str(sheet)
            return
        if not fetch.section_360(url, max(0.0, s - 1), e + 1, piece, cookies):
            it["sheet"] = None
            return
        fps = 2 if e - s <= 30 else 1
        frames = math.ceil((e - s + 2) * fps)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(piece), "-vf",
                        f"fps={fps},scale=240:-2,drawtext=text='%{{pts\\:hms\\:{max(0.0, s - 1):.2f}}}':x=4:y=4:fontsize=14:"
                        f"fontcolor=yellow:box=1:boxcolor=black@0.6,tile=8x{math.ceil(frames / 8)}",
                        "-frames:v", "1", str(sheet)], capture_output=True)
        it["sheet"] = str(sheet) if sheet.exists() else None

    with cf.ThreadPoolExecutor(3) as ex:
        list(ex.map(one, items))


_SLUG = re.compile(r"[^a-z0-9]+")


def finalize(job_path: pathlib.Path, job_cfg: dict, r: dict, short: list[dict], selection: dict, backup_dir: pathlib.Path) -> int:
    by_id = {s["id"]: s for s in short}
    clips = []
    for i, sel in enumerate(selection.get("clips") or [], 1):
        base = by_id.get(sel.get("id"))
        if not base:
            raise SystemExit(f"selection.json: unknown id {sel.get('id')!r} (shortlist ids: {', '.join(by_id)})")
        m = {**base, **{k: v for k, v in sel.items() if v not in (None, "")}}
        kind = r["kinds"][m["kind"]]
        slug = _SLUG.sub("_", (m.get("slug") or m.get("title") or m["id"]).lower()).strip("_")[:40]
        tags = list(dict.fromkeys(list(r.get("hashtags") or []) + list(m.get("hashtags") or [])))
        clips.append({
            "id": i, "slug": slug, "label": m.get("label") or m.get("title") or slug,
            "start": hmsf(parse_t(m["start"])), "end": hmsf(parse_t(m["end"])),
            "title": m.get("title", ""), "caption": m.get("caption", ""),
            **({"hashtags": " ".join(tags)} if tags else {}),
            "audio": {"source": kind.get("audio", "original")},
            "edit": bool(kind.get("edit", True)),
            "hint": {"kind": m["kind"], "payoff": m.get("payoff"), "hook": m.get("hook", ""), "why": m.get("why", ""),
                     "score": m.get("score")},
        })
    if not clips:
        raise SystemExit("selection.json has no clips")
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / f"{job_path.stem}.before-finalize.json").write_text(job_path.read_text())
    cfg = json.loads(job_path.read_text())
    cfg["clips"] = clips
    job_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    return len(clips)


def report(short: list[dict], url: str, path: pathlib.Path) -> None:
    rows = ["| id | kind | score | start - end | len | payoff | hook | preview |", "|---|---|---|---|---|---|---|---|"]
    for s in short:
        t = int(parse_t(s["start"]))
        link = f"{url}{'&' if '?' in url else '?'}t={t}s"
        rows.append(f"| {s['id']} | {s['kind']} | {s['score']} | {s['start']} - {s['end']} | {s['length']}s | "
                    f"{s.get('payoff') or ''} | {s['hook']} | {link} |")
    path.write_text("# Shortlist\n\n" + "\n".join(rows) + "\n")


__all__ = ["hms"]
