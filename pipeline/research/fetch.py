"""Everything research downloads, each step cached in workspace/<job>/research/raw/.

Nothing here downloads video except verify sheets (low res, only shortlisted
minutes). Audio is the lowest-bitrate track: enough for loudness.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

from ..stages import VENV_BIN, env


def ytdlp() -> list[str]:
    p = VENV_BIN / "yt-dlp"
    return [str(p) if p.exists() else "yt-dlp", "--no-warnings"]


def _run(args: list, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env(), capture_output=True, text=True)


def cookie_args(cfg: dict) -> list[str]:
    c = cfg.get("cookies_file") or cfg.get("cookies_browser") or ""
    if not c:
        return []
    return ["--cookies", c] if pathlib.Path(c).is_file() else ["--cookies-from-browser", c]


def platform(url: str) -> str:
    u = url.lower()
    return "youtube" if ("youtube.com" in u or "youtu.be" in u) else "twitch" if "twitch.tv" in u else "kick" if "kick.com" in u else "other"


# ---------------------------------------------------------------- metadata


def meta(url: str, raw: pathlib.Path, cookies: list[str]) -> dict:
    f = raw / "meta.json"
    if f.exists():
        return json.loads(f.read_text())
    r = _run(ytdlp() + cookies + ["-J", "--no-playlist", url])
    if r.returncode != 0:
        raise SystemExit(f"could not read the video: {(r.stderr or '').strip().splitlines()[-1:]}")
    d = json.loads(r.stdout)
    keep = {k: d.get(k) for k in ("id", "title", "channel", "uploader", "duration", "language", "was_live",
                                  "live_status", "webpage_url", "heatmap", "chapters", "comment_count", "extractor_key")}
    keep["auto_caption_langs"] = sorted((d.get("automatic_captions") or {}).keys())
    keep["subtitle_langs"] = sorted((d.get("subtitles") or {}).keys())
    raw.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(keep, indent=1))
    return keep


# ---------------------------------------------------------------- captions


def _caption_choices(m: dict, prefs: list[str]) -> list[tuple[str, bool]]:
    """(language code, is_auto) in preference order, only those the video has."""
    subs, auto = set(m["subtitle_langs"]), set(m["auto_caption_langs"])
    out = []
    for p in prefs:
        if p == "orig":
            lang = m.get("language")
            if lang and lang in subs:
                out.append((lang, False))
            out += [(a, True) for a in sorted(auto) if a.endswith("-orig")]
        elif p in subs:
            out.append((p, False))
        elif p in auto:
            out.append((p, True))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def captions(url: str, m: dict, raw: pathlib.Path, prefs: list[str], cookies: list[str]) -> tuple[pathlib.Path | None, str]:
    done = raw / "captions.json"
    if done.exists():
        info = json.loads(done.read_text())
        return (raw / info["file"]) if info.get("file") else None, info.get("note", "")
    tried = []
    for lang, is_auto in _caption_choices(m, prefs):
        for attempt in range(3):
            args = ytdlp() + cookies + ["--skip-download", "--sub-format", "json3", "--sub-langs", lang,
                                        "--write-auto-subs" if is_auto else "--write-subs", "-o", raw / "cap", url]
            r = _run(args)
            got = next(iter(raw.glob(f"cap.{lang}.json3")), None)
            if got:
                note = f"{lang} ({'auto' if is_auto else 'manual'})"
                done.write_text(json.dumps({"file": got.name, "lang": lang, "auto": is_auto, "note": note}))
                return got, note
            if "429" in (r.stderr or "") and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            tried.append(f"{lang}: {'429 rate-limited' if '429' in (r.stderr or '') else 'failed'}")
            break
    note = "no captions (" + ("; ".join(tried) if tried else "none offered") + ")"
    done.write_text(json.dumps({"file": None, "note": note}))
    return None, note


# ---------------------------------------------------------------- comments, chat


_TS = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")


def comments(url: str, raw: pathlib.Path, max_comments: int, duration: float, cookies: list[str]) -> list[dict]:
    """Timestamp mentions in comments: [{t, likes, text}]."""
    f = raw / "comment_mentions.json"
    if f.exists():
        return json.loads(f.read_text())
    r = _run(ytdlp() + cookies + ["--skip-download", "--write-comments", "--no-write-info-json",
                                  "--extractor-args", f"youtube:max_comments={max_comments};comment_sort=top",
                                  "-J", url])
    out = []
    seen: dict[str, int] = {}
    if r.returncode == 0:
        for c in json.loads(r.stdout).get("comments") or []:
            text = (c.get("text") or "").replace("\n", " ")
            likes = int(c.get("like_count") or 0)
            key = re.sub(r"\W+", "", text.lower())[:80]
            if key in seen and seen[key] >= likes:  # copy-pasted spam counts once
                continue
            seen[key] = likes
            stamps = []
            for mt in _TS.finditer(text):
                h, mm, ss = mt.groups()
                t = int(h or 0) * 3600 + int(mm) * 60 + int(ss)
                if int(mm) < 60 and int(ss) < 60 and t < duration:
                    stamps.append(t)
            for t in stamps:  # n = how many moments this comment points at (index lists point at many)
                out.append({"t": t, "likes": likes, "n": len(stamps), "text": text[:120]})
    f.write_text(json.dumps(out))
    return out


def chat(url: str, raw: pathlib.Path, cookies: list[str]) -> list[float]:
    """YouTube replay chat message times (seconds)."""
    f = raw / "chat_times.json"
    if f.exists():
        return json.loads(f.read_text())
    _run(ytdlp() + cookies + ["--skip-download", "--write-subs", "--sub-langs", "live_chat", "-o", raw / "chat", url])
    times = []
    src = next(iter(raw.glob("chat*.live_chat.json")), None)
    if src:
        for line in open(src, encoding="utf-8", errors="replace"):
            try:
                times.append(int(json.loads(line)["replayChatItemAction"]["videoOffsetTimeMsec"]) / 1000)
            except Exception:
                pass
        src.unlink()
    f.write_text(json.dumps(times))
    return times


# ---------------------------------------------------------------- audio


def audio(url: str, raw: pathlib.Path, cookies: list[str]) -> pathlib.Path | None:
    have = [p for p in raw.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if have:
        return have[0]
    # plain https (HLS fragments crawl), and not the -drc tracks: dynamic-range compression
    # flattens the loudness signal
    r = _run(ytdlp() + cookies + ["-q", "--no-playlist", "-N", "8",
                                  "-f", "worstaudio[protocol^=https][format_id!*=drc]/worstaudio[format_id!*=drc]/worstaudio",
                                  "-o", raw / "audio.%(ext)s", url])
    have = [p for p in raw.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if not have:  # Twitch highlights / edited VODs: yt-dlp's HLS downloader breaks, ffmpeg's works
        _run(ytdlp() + cookies + ["-q", "--no-playlist", "--downloader", "m3u8:ffmpeg", "-f", "worstaudio/bestaudio",
                                  "-o", raw / "audio.%(ext)s", url])
        have = [p for p in raw.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    return have[0] if have else None


def section_360(url: str, start: float, end: float, out: pathlib.Path, cookies: list[str]) -> bool:
    """A low-res video piece for a verify sheet."""
    if out.exists():
        return True
    def hms(s):
        return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"
    r = _run(ytdlp() + cookies + ["-q", "--no-playlist", "-f", "bv*[height<=360]+ba/b[height<=360]/worst",
                                  "--download-sections", f"*{hms(start)}-{hms(end)}", "--merge-output-format", "mp4",
                                  "-o", out, url])
    return out.exists() and r.returncode == 0
