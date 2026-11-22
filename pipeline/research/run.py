"""`python3 -m pipeline research jobs/<job>.json`: video URL -> clips in the job.

Resumable, with two AI gates (see .claude/skills/clip-pipeline/references/picking.md):

    meta, captions, comments, chat, audio   cached in research/raw/
    timeline -> windows -> chunks/w*.md     what the AI reads
    gate 1: picks/w*.json                   one per window, [] when nothing qualifies
    shortlist + verify sheets + report.md
    gate 2: selection.json                  the final clips, in order
    finalize                                clips written into the job (backup kept)
"""

from __future__ import annotations

import json
import pathlib

from . import config, fetch, select, signals, text, windows

GUIDE = ("Read `.claude/skills/clip-pipeline/references/picking.md` before the first window. Brief: {brief}\n"
         "Kinds: {kinds}.\n"
         "Markers: CMT = viewers timestamped this in comments (likes-weighted), REPLAYED = YouTube most-replayed, "
         "CHAT xN = chat N times faster than usual, "
         "LOUD +NdB = the speaker is that much louder than usual, FAST TALK = talking far more than usual. "
         "Signals point; they don't decide. Times are stream time.")


def _say(msg=""):
    print(msg, flush=True)


def run(job, rescan: bool = False) -> None:
    r = config.resolve(job.cfg)
    url = job.cfg["video_url"]
    ck = fetch.cookie_args(job.cfg)
    rd = job.ws / "research"
    raw = rd / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    m = fetch.meta(url, raw, ck)
    dur = float(m.get("duration") or 0)
    plat = fetch.platform(url)
    _say(f"stream: {m.get('title')!r} by {m.get('channel') or m.get('uploader')}, {windows.hms(dur)}, language {m.get('language') or '?'}")

    # ---- transcript
    cap, note = fetch.captions(url, m, raw, r["captions"], ck)
    lines = text.json3_lines(cap) if cap else []
    roman = r["romanize"] and text.needs_romanize(lines)
    _say(f"captions: {note}; {len(lines)} lines" + ("; romanized for reading" if roman else ""))

    # ---- signals
    n = signals.nbins(dur)
    series, rawstats = {}, {"loud_db_over": [0.0] * n}
    words, series["speech"] = signals.speech(lines, n)
    mentions, by_bin = [], {}
    sig = r["signals"]
    if sig.get("comments") and plat == "youtube":
        mentions = fetch.comments(url, raw, int(sig.get("max_comments", 2000)), dur, ck)
        series["comments"], by_bin = signals.comments(mentions, n)
    if sig.get("chat") and plat == "youtube":
        series["chat"] = signals.chat(fetch.chat(url, raw, ck), n)
    if sig.get("heatmap"):
        series["heatmap"] = signals.heatmap(m.get("heatmap"), n)
    if sig.get("audio"):
        cache = raw / "audio_signals.json"
        if cache.exists():
            a = json.loads(cache.read_text())
        else:
            _say("audio: downloading the lowest-bitrate track to measure speaker loudness...")
            ap = fetch.audio(url, raw, ck)
            a = None
            if ap:
                loud, st = signals.audio(ap, n, words)
                a = {"loud": loud, **st}
                cache.write_text(json.dumps(a))
                ap.unlink(missing_ok=True)
        if a and "loud" in a:
            series["loud"] = a["loud"]
            rawstats = {"loud_db_over": a["loud_db_over"]}
    have = [k for k, v in series.items() if v and any(v)]
    _say(f"signals: {', '.join(have) or 'none'}" + (f"; {len(mentions)} comment timestamps" if mentions else ""))
    combined = signals.combine(series, r["weights"], n)
    (rd / "timeline.json").write_text(json.dumps({"bin": signals.BIN, "combined": combined, **series}))

    # ---- windows + chunks (stable once made, so picks keep matching their window)
    wfile = rd / "windows.json"
    if rescan or not wfile.exists():
        wins = (windows.hot(combined, int(r["windows"]), float(r["window_sec"]), dur) if r["scan"] == "hot"
                else windows.full(dur, float(r["chunk_min"])))
        kinds = "; ".join(f"{k} {v['length'][0]}-{v['length'][1]}s ({v.get('means', '')})" for k, v in r["kinds"].items())
        header = f"# {m.get('title')} ({m.get('channel') or m.get('uploader')}, {windows.hms(dur)})"
        guide = GUIDE.format(brief=r["brief"] or "(none: pick what a viewer would share)", kinds=kinds)
        windows.write(wins, lines, series, rawstats, by_bin, rd / "chunks", header, guide,
                      text.romanize if roman else (lambda s: s))
        wfile.write_text(json.dumps(wins, indent=1))
        _say(f"windows: {len(wins)} {'hot windows' if r['scan'] == 'hot' else 'chunks'} written to {rd / 'chunks'}")
    wins = json.loads(wfile.read_text())

    # ---- gate 1: picks
    picks = rd / "picks"
    picks.mkdir(exist_ok=True)
    missing = [w["name"] for w in wins if not (picks / f"{w['name']}.json").exists()]
    if missing:
        _say(f"\nNEEDS PICKS: {len(missing)} of {len(wins)} windows -> read chunks/<w>.md, write picks/<w>.json")
        _say(f"  {rd / 'chunks'}: {', '.join(missing)}")
        return

    # ---- shortlist + verify
    sfile = rd / "shortlist.json"
    newest_pick = max((p.stat().st_mtime for p in picks.glob("w*.json")), default=0)
    if not sfile.exists() or newest_pick > sfile.stat().st_mtime:
        cands, problems = select.load_picks(picks, r["kinds"], dur)
        for pr in problems:
            _say(f"  pick problem: {pr}")
        short = select.shortlist(cands, r, lines)
        if len(short) < int(r["count"]):
            _say(f"  only {len(short)} moments scored >= {r['min_score']} (wanted {r['count']}); "
                 "say so to the person and offer a lower min_score rather than lowering it quietly")
        if r["verify"] and short:
            _say(f"verify: 360p contact sheets for {len(short)} moments...")
            select.verify_sheets(short, url, rd / "verify", ck)
        sfile.write_text(json.dumps(short, indent=1, ensure_ascii=False))
        select.report(short, m.get("webpage_url") or url, rd / "report.md")
    short = json.loads(sfile.read_text())

    # ---- gate 2: selection
    sel = rd / "selection.json"
    if not sel.exists() or sel.stat().st_mtime < sfile.stat().st_mtime:
        _say(f"\nNEEDS SELECTION: {len(short)} shortlisted ({rd / 'report.md'}); check each verify sheet "
             f"({rd / 'verify'}/<id>.jpg), then write {sel}")
        return

    # ---- finalize
    marker = rd / "finalized.json"
    if marker.exists() and marker.stat().st_mtime >= sel.stat().st_mtime:
        _say(f"\nresearch done: {json.loads(marker.read_text())['clips']} clips in {job.path.name}; next: python3 -m pipeline run {job.path.name and job.path}")
        return
    count = select.finalize(job.path, job.cfg, r, short, json.loads(sel.read_text()), rd)
    marker.write_text(json.dumps({"clips": count}))
    _say(f"\nresearch done: {count} clips written to {job.path} (previous version in {rd}); next: python3 -m pipeline run {job.path}")
