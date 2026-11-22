#!/usr/bin/env python3
"""
Hardened Batch Shorts Clipper Engine v2.0 (`pipeline/clipper.py`, formerly shorts_clipper.py)

Normally driven by the pipeline (`python3 -m pipeline run jobs/<job>.json`), which
points output_dir into workspace/ and always keeps the raw downloads.
Dedicated, config-driven tool for extracting and rendering multiple standalone
1080x1920 vertical Shorts from any YouTube/Twitch/Kick stream.

v2.0 Audio-Isolation & Hardening Features:
  - Audio isolation engines (`audio.isolation_engine`: auto | audio_separator | demucs | ffmpeg_vocal_cut):
      * Never silently falls back to raw commentary — automatically engages built-in FFmpeg
        center-channel vocal suppression + speech-band EQ when AI separators aren't installed
      * Supports stacking post-separation speech-band EQ to kill loud streamer shout bleed
      * Optional `edge-tts` English hook/title voiceover + background music bed (`bgm_path`)
  - `--check` diagnostic command reporting installed tools & audio engines
  - Upfront JSON schema & timestamp validation, yt-dlp retries with backoff, smart resume-skip,
    per-clip fault isolation, bounded silent-source handling, +faststart MP4, per-clip
    verification thumbnails (`verify_frames/`), and `run_report.json`

Usage:
    python -m pipeline.clipper --check
    python -m pipeline.clipper --self-test
    python -m pipeline.clipper --config jobs/carry_gta6.json
    python -m pipeline.clipper --config jobs/carry_gta6.json --clips 1 3 9
    python -m pipeline.clipper --config jobs/carry_gta6.json --cookies firefox --bgm phonk.mp3
    python -m pipeline.clipper --config jobs/carry_gta6.json --isolation-engine ffmpeg_vocal_cut
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any

VERSION = "2.0.0"
# what is kept of the stream's own sound
SOURCES = ("original", "no_voice", "voice_only", "muted")
LEGACY_MODES = {"gunshots": "no_voice", "bgm": "muted", "original": "original"}  # old audio.mode values

TIME_RE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d(?:\.\d+)?)$")


def parse_timestamp(ts: str) -> float:
    m = TIME_RE.match(ts.strip())
    if not m:
        raise ValueError(f"Invalid timestamp '{ts}' (expected HH:MM:SS or MM:SS)")
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def validate_config(cfg: dict[str, Any]) -> None:
    url = cfg.get("video_url") or cfg.get("source_url") or ""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("Config requires a valid http(s) 'video_url'.")
    cfg["video_url"] = url

    clips = cfg.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("Config requires a non-empty 'clips' list.")

    seen_ids: set[int] = set()
    for idx, c in enumerate(clips, start=1):
        cid = c.get("id")
        if not isinstance(cid, int) or cid in seen_ids:
            raise ValueError(f"Clip #{idx} must have a unique integer 'id'.")
        seen_ids.add(cid)
        if not c.get("slug") or not c.get("label"):
            raise ValueError(f"Clip id={cid} requires non-empty 'slug' and 'label'.")
        dur = parse_timestamp(str(c.get("end", ""))) - parse_timestamp(str(c.get("start", "")))
        if dur <= 1.0 or dur > 180.0:
            raise ValueError(f"Clip id={cid} duration ({dur:.1f}s) must be between 1s and 180s.")

    crop = cfg.setdefault("crop", {})
    tt = float(crop.get("trim_top", 0.04))
    tb = float(crop.get("trim_bottom", 0.10))
    xo = float(crop.get("x_offset", 0.0))
    if not (0.0 <= tt < 0.5 and 0.0 <= tb < 0.5 and tt + tb < 0.7):
        raise ValueError(f"Invalid crop trim values: trim_top={tt}, trim_bottom={tb}")
    if not (-0.4 <= xo <= 0.4):
        raise ValueError(f"Invalid crop x_offset={xo}")

    audio = cfg.setdefault("audio", {})
    if "source" not in audio:
        mode = audio.get("mode", "gunshots")
        if mode not in LEGACY_MODES:
            raise ValueError(f"Invalid audio.mode '{mode}' (use audio.source: {', '.join(SOURCES)})")
        audio["source"] = LEGACY_MODES[mode]
    if audio["source"] not in SOURCES:
        raise ValueError(f"Invalid audio.source '{audio['source']}' (expected {', '.join(SOURCES)})")
    on_fail = audio.setdefault("on_fail", "ffmpeg_cut")
    if on_fail not in ("ffmpeg_cut", "original", "error"):
        raise ValueError(f"Invalid audio.on_fail '{on_fail}' (expected ffmpeg_cut, original or error)")
    for c in clips:
        src = (c.get("audio") or {}).get("source")
        if src and src not in SOURCES:
            raise ValueError(f"Clip id={c['id']}: invalid audio.source '{src}' (expected {', '.join(SOURCES)})")
    eng = audio.setdefault("isolation_engine", "auto")
    if eng not in ("auto", "audio_separator", "demucs", "ffmpeg_vocal_cut"):
        raise ValueError(f"Invalid audio.isolation_engine '{eng}'")
    strength = audio.setdefault("vocal_cut_strength", "aggressive")
    if strength not in ("moderate", "aggressive"):
        raise ValueError(f"Invalid audio.vocal_cut_strength '{strength}'")

    cfg.setdefault("fx", {"enabled": True, "show_title": True})

    dl = cfg.setdefault("download", {})
    max_h = dl.setdefault("max_height", 1440)
    if max_h not in (720, 1080, 1440, 2160):
        raise ValueError(f"Invalid download.max_height {max_h} (expected 720, 1080, 1440 or 2160)")


def find_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\ariblk.ttf",
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/mnt/c/Windows/Fonts/ariblk.ttf",
        "/mnt/c/Windows/Fonts/impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def find_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    root = pathlib.Path(__file__).resolve().parent.parent
    candidates = [
        root / ".venv" / "bin" / name,
        pathlib.Path.home() / ".local" / "bin" / name,
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def check_environment() -> dict[str, Any]:
    has_sep = bool(find_binary("audio-separator"))
    demucs_bin = find_binary("demucs")
    has_demucs = bool(demucs_bin)
    has_tts = bool(find_binary("edge-tts"))
    recommended = "demucs" if has_demucs else ("audio_separator" if has_sep else "ffmpeg_vocal_cut")
    warnings: list[str] = []
    if not has_sep and not has_demucs:
        warnings.append(
            "Neither 'audio-separator' nor 'demucs' is installed. Gunshots mode will use built-in "
            "FFmpeg Center-Channel Vocal Suppression + Speech-Band EQ (zero-install). For cleanest "
            "AI commentary removal, run: pip install audio-separator[cpu]  (or: pip install demucs)"
        )
    return {
        "version": VERSION,
        "platform": platform.system(),
        "python": platform.python_version(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "yt_dlp": bool(shutil.which("yt-dlp")),
        "audio_separator": has_sep,
        "demucs": has_demucs,
        "demucs_path": demucs_bin,
        "edge_tts": has_tts,
        "font": find_font(),
        "recommended_engine": recommended,
        "warnings": warnings,
    }


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def format_font_arg(font_path: str) -> str:
    if not font_path:
        return ""
    escaped = font_path.replace("\\", "/").replace(":", r"\:")
    return f"fontfile='{escaped}':"


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)


def probe_media(path: pathlib.Path) -> tuple[float, bool]:
    """Return (duration_seconds, has_audio_stream). Returns (0.0, False) if unreadable."""
    if not path.exists() or path.stat().st_size == 0:
        return 0.0, False
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(path),
        ], text=True)
        info = json.loads(out)
        dur = float(info.get("format", {}).get("duration", 0.0))
        has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        return dur, has_audio
    except Exception:
        return 0.0, False


def generate_open_sfx(work_dir: pathlib.Path) -> pathlib.Path:
    sfx_path = work_dir / "open_sfx.wav"
    if sfx_path.exists():
        return sfx_path
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", "aevalsrc=0.55*sin(2*PI*(145-90*t)*t)*exp(-10*t)+0.22*sin(2*PI*500*t)*exp(-18*t):d=0.30:s=48000",
        "-ac", "2", str(sfx_path),
    ])
    return sfx_path


def generate_tts(text: str, voice: str, rate: str, out_wav: pathlib.Path) -> pathlib.Path | None:
    tts_bin = find_binary("edge-tts")
    if not text.strip() or not tts_bin:
        return None
    mp3_tmp = out_wav.with_suffix(".mp3")
    try:
        run([tts_bin, "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(mp3_tmp)])
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3_tmp), "-ar", "48000", "-ac", "2", str(out_wav)])
        mp3_tmp.unlink(missing_ok=True)
        return out_wav
    except Exception as exc:
        print(f"[warn] TTS generation failed for '{text[:30]}...': {exc}")
        mp3_tmp.unlink(missing_ok=True)
        return None


def vocal_suppression_filter(strength: str) -> str:
    """FFmpeg center-channel vocal suppression + speech-band EQ (keeps stereo gunshots/explosions)."""
    if strength == "moderate":
        return (
            "highpass=f=55,"
            "stereotools=mode=ms>lr:sbal=0:mlev=0.35:slev=1.25,"
            "equalizer=f=1100:t=q:w=1.1:g=-8,"
            "equalizer=f=2400:t=q:w=1.2:g=-6,"
            "lowshelf=f=140:g=3"
        )
    return (
        "highpass=f=60,"
        "stereotools=mode=ms>lr:sbal=0:mlev=0.12:slev=1.45,"
        "equalizer=f=420:t=q:w=1.2:g=-9,"
        "equalizer=f=1200:t=q:w=1.0:g=-14,"
        "equalizer=f=2600:t=q:w=1.2:g=-10,"
        "lowshelf=f=130:g=4"
    )


def run_ai_vocal_strip(raw_path: pathlib.Path, audio_cfg: dict[str, Any], work_dir: pathlib.Path,
                       stem: str = "no_vocals") -> tuple[pathlib.Path | None, str]:
    """AI voice separation. stem="no_vocals" keeps everything but the voice, "vocals" only the voice."""
    engine = audio_cfg.get("isolation_engine", "auto")
    strict = bool(audio_cfg.get("strict_isolation", False))
    wav_in = work_dir / f"{raw_path.stem}_orig.wav"

    def ensure_wav() -> pathlib.Path:
        if not wav_in.exists():
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path), "-vn", "-ac", "2", "-ar", "44100", str(wav_in)])
        return wav_in

    # 1. audio-separator (UVR MDX-Net)
    sep_bin = find_binary("audio-separator")
    if engine in ("auto", "audio_separator") and sep_bin:
        sep_dir = work_dir / f"sep_{raw_path.stem}"
        sep_dir.mkdir(exist_ok=True)
        model = audio_cfg.get("audio_separator_model", "UVR-MDX-NET-Inst_HQ_3.onnx")
        want = "Instrumental" if stem == "no_vocals" else "Vocals"
        run([sep_bin, str(ensure_wav()), "--model_filename", model, "--output_dir", str(sep_dir), "--single_stem", want])
        matches = list(sep_dir.glob(f"*{want}*.wav")) + list(sep_dir.glob(f"*{want}*.flac"))
        if matches:
            return matches[0], "audio_separator"

    # 2. demucs
    demucs_bin = find_binary("demucs")
    if engine in ("auto", "demucs") and demucs_bin:
        demucs_out = work_dir / "demucs_out"
        matches = list(demucs_out.rglob(f"{wav_in.stem}/{stem}.*"))
        if not matches:  # one demucs pass writes both stems; reuse it
            run([demucs_bin, "--two-stems=vocals", "-o", str(demucs_out), str(ensure_wav())])
            matches = list(demucs_out.rglob(f"{wav_in.stem}/{stem}.*"))
        if matches:
            return matches[0], "demucs"

    if strict and engine != "ffmpeg_vocal_cut":
        raise RuntimeError(
            "strict_isolation=true but neither 'audio-separator' nor 'demucs' is installed. "
            "Install via `pip install audio-separator[cpu]` or set isolation_engine='ffmpeg_vocal_cut'."
        )

    if engine != "ffmpeg_vocal_cut":
        print("[warn] No AI separator found (audio-separator/demucs); using built-in FFmpeg Center-Channel Vocal Suppression + Speech-Band EQ.")
    return None, "ffmpeg_vocal_cut"


def download_segment(
    url: str,
    clip: dict[str, Any],
    work_dir: pathlib.Path,
    cookies: str | None,
    retries: int,
    max_height: int = 1440,
) -> pathlib.Path:
    out_file = work_dir / f"raw_{clip['id']:02d}.mp4"
    # sidecar records the max height a raw file was fetched at, so raising
    # download.max_height re-fetches old lower-res downloads once
    stamp = out_file.with_name(out_file.name + ".maxh")
    dur, _ = probe_media(out_file)
    if dur > 1.0 and stamp.exists() and stamp.read_text().strip() == str(max_height):
        return out_file

    h = max_height
    node_bin = shutil.which("node")
    cmd = [
        "yt-dlp",
    ]
    if node_bin:
        cmd += ["--js-runtimes", f"node:{node_bin}"]
    cmd += [
        # best stream up to max_height in any codec (1440p+ on YouTube is VP9/AV1), merged to mp4
        "-f", f"bestvideo[height<={h}]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
        "--download-sections", f"*{clip['start']}-{clip['end']}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_file),
    ]
    if cookies:
        if os.path.isfile(cookies):
            cmd += ["--cookies", cookies]
        else:
            cmd += ["--cookies-from-browser", cookies]
    cmd.append(url)

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if out_file.exists():
                out_file.unlink()
            run(cmd)
            dur, _ = probe_media(out_file)
            if dur > 1.0:
                stamp.write_text(str(max_height))
                return out_file
            raise RuntimeError(f"Downloaded file invalid or too short ({dur:.2f}s)")
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                wait = 2 ** attempt
                print(f"[warn] Download attempt {attempt}/{retries} failed for clip {clip['id']}: {exc}. Retrying in {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"Download failed after {retries} attempts: {last_err}")


def build_video_filters(clip: dict[str, Any], cfg: dict[str, Any], font_arg: str) -> str:
    crop = cfg["crop"]
    trim_top = float(crop.get("trim_top", 0.04))
    trim_bottom = float(crop.get("trim_bottom", 0.10))
    x_offset = float(crop.get("x_offset", 0.0))

    usable_h = f"ih*(1-{trim_top + trim_bottom:.3f})"
    crop_w = f"min(iw\\,({usable_h})*9/16)"
    crop_x = f"max(0\\,min(iw-{crop_w}\\,(iw-{crop_w})/2+iw*{x_offset:.3f}))"
    crop_y = f"ih*{trim_top:.3f}"

    filters = [
        f"crop=w={crop_w}:h={usable_h}:x={crop_x}:y={crop_y}",
        "scale=1080:1920:flags=lanczos",
        "fps=30",
        "setsar=1",
    ]
    if cfg["fx"].get("enabled", True):
        filters.extend([
            "eq=contrast=1.08:saturation=1.18:brightness=0.02",
            "unsharp=5:5:0.7:5:5:0.0",
            "vignette=PI/6",
            "drawbox=x=0:y=0:w=1080:h=1920:color=white@0.24:t=fill:enable='lt(t,0.14)'",
        ])

    if cfg["fx"].get("show_title", True):
        label = clip["label"].upper()
        fontsize = 52 if len(label) <= 22 else (44 if len(label) <= 28 else 36)
        filters.extend([
            "drawbox=x=0:y=0:w=1080:h=175:color=black@0.55:t=fill",
            (
                f"drawtext={font_arg}text='{escape_drawtext(label)}':"
                f"fontcolor=white:fontsize={fontsize}:borderw=4:bordercolor=black:"
                "x=(w-text_w)/2:y=62"
            ),
        ])
    return ",".join(filters)


def build_audio_chain(
    clip: dict[str, Any],
    raw_path: pathlib.Path,
    raw_dur: float,
    has_audio: bool,
    cfg: dict[str, Any],
    sfx_path: pathlib.Path | None,
    work_dir: pathlib.Path,
) -> tuple[list[str], str, str]:
    audio_cfg = cfg["audio"]
    source = audio_cfg["source"]
    on_fail = audio_cfg.get("on_fail", "ffmpeg_cut")
    bgm_path = audio_cfg.get("bgm_path") or audio_cfg.get("bgm") or ""
    bgm_vol = float(audio_cfg.get("bgm_volume", audio_cfg.get("bgm_vol", 0.28)))
    sfx_vol = float(audio_cfg.get("sfx_volume", 0.85))
    strength = audio_cfg.get("vocal_cut_strength", "aggressive")
    post_eq = bool(audio_cfg.get("post_vocal_suppression", True))

    extra_inputs: list[str] = []
    next_idx = 1
    mix_labels: list[str] = []
    parts: list[str] = []
    used_engine = source

    if has_audio and source in ("no_voice", "voice_only"):
        stem = "no_vocals" if source == "no_voice" else "vocals"
        ai_wav, engine = run_ai_vocal_strip(raw_path, audio_cfg, work_dir, stem)
        used_engine = engine if source == "no_voice" else f"voice_only/{engine}"
        if ai_wav:
            extra_inputs += ["-i", str(ai_wav)]
            src_in = f"[{next_idx}:a]"
            next_idx += 1
            eq_chain = f",{vocal_suppression_filter('moderate')}" if (post_eq and source == "no_voice") else ""
        elif on_fail == "error":
            raise RuntimeError(f"audio.source={source} needs demucs or audio-separator, and neither worked (audio.on_fail=error)")
        elif on_fail == "original":
            print(f"[warn] voice separation unavailable: keeping the original sound (audio.on_fail=original)")
            src_in, eq_chain, used_engine = "[0:a]", "", f"{source}->original"
        else:
            src_in = "[0:a]"
            eq_chain = (f",{vocal_suppression_filter(strength)}" if source == "no_voice"
                        else ",pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1,highpass=f=120,lowpass=f=7000")
        parts.append(f"{src_in}aresample=48000,aformat=channel_layouts=stereo{eq_chain},loudnorm=I=-14:TP=-1.5:LRA=11[g]")
        mix_labels.append("[g]")
    elif has_audio and source == "original":
        parts.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[g]")
        mix_labels.append("[g]")

    if sfx_path and audio_cfg.get("sfx_enabled", True):
        extra_inputs += ["-i", str(sfx_path)]
        parts.append(f"[{next_idx}:a]volume={sfx_vol:.2f},aresample=48000[s]")
        mix_labels.append("[s]")
        next_idx += 1

    if audio_cfg.get("tts_enabled", False):
        tts_text = clip.get("tts_text") or clip.get("label", "")
        tts_wav = generate_tts(
            tts_text,
            audio_cfg.get("tts_voice", "en-US-ChristopherNeural"),
            audio_cfg.get("tts_rate", "+8%"),
            work_dir / f"tts_{clip['id']:02d}.wav",
        )
        if tts_wav:
            extra_inputs += ["-i", str(tts_wav)]
            delay_ms = int(float(audio_cfg.get("tts_delay_sec", 0.15)) * 1000)
            tts_vol = float(audio_cfg.get("tts_volume", 1.25))
            parts.append(f"[{next_idx}:a]adelay={delay_ms}|{delay_ms},volume={tts_vol:.2f},aresample=48000[t]")
            mix_labels.append("[t]")
            next_idx += 1

    if bgm_path and os.path.isfile(bgm_path):
        extra_inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        parts.append(f"[{next_idx}:a]volume={bgm_vol:.2f},aresample=48000,atrim=0:{raw_dur:.3f}[b]")
        mix_labels.append("[b]")
        next_idx += 1

    if not mix_labels:
        parts.append(f"anullsrc=r=48000:cl=stereo:d={raw_dur:.3f}[aout]")
    elif len(mix_labels) == 1:
        parts.append(f"{mix_labels[0]}apad=whole_dur={raw_dur:.3f},atrim=0:{raw_dur:.3f},alimiter=limit=0.95[aout]")
    else:
        parts.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0,"
            f"apad=whole_dur={raw_dur:.3f},atrim=0:{raw_dur:.3f},alimiter=limit=0.95[aout]"
        )

    return extra_inputs, ";".join(parts), used_engine


def render_clip(
    clip: dict[str, Any],
    raw_path: pathlib.Path,
    out_path: pathlib.Path,
    verify_dir: pathlib.Path,
    cfg: dict[str, Any],
    font_arg: str,
    sfx_path: pathlib.Path | None,
    work_dir: pathlib.Path,
) -> dict[str, Any]:
    raw_dur, has_audio = probe_media(raw_path)
    if raw_dur <= 0.5:
        raise RuntimeError(f"Source segment unreadable: {raw_path}")

    vf = build_video_filters(clip, cfg, font_arg)
    extra_inputs, afc, used_engine = build_audio_chain(clip, raw_path, raw_dur, has_audio, cfg, sfx_path, work_dir)
    tmp_out = out_path.with_suffix(".tmp.mp4")

    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(raw_path),
        *extra_inputs,
        "-filter_complex", f"[0:v]{vf}[vout];{afc}",
        "-map", "[vout]", "-map", "[aout]",
        "-movflags", "+faststart",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(tmp_out),
    ])
    tmp_out.replace(out_path)

    out_dur, _ = probe_media(out_path)
    if out_dur <= 0.5:
        raise RuntimeError("Rendered output failed integrity check.")

    hashtags = clip.get("hashtags") or cfg.get("default_hashtags", "#Shorts")
    meta = f"TITLE:\n{clip.get('title', clip['label'])}\n\nCAPTION:\n{clip.get('caption', '')}\n\nHASHTAGS:\n{hashtags}\n"
    out_path.with_suffix(".txt").write_text(meta, encoding="utf-8")

    thumb_t = min(2.0, max(0.2, out_dur / 2.0))
    thumb_path = verify_dir / f"clip_{clip['id']:02d}.jpg"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{thumb_t:.2f}", "-i", str(out_path),
        "-vframes", "1", str(thumb_path),
    ])

    return {
        "id": clip["id"],
        "file": out_path.name,
        "duration_s": round(out_dur, 2),
        "size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
        "audio_engine": used_engine,
        "thumbnail": str(thumb_path.relative_to(out_path.parent)),
        "status": "rendered",
    }


def run_self_test(cfg: dict[str, Any] | None = None) -> None:
    tmp = pathlib.Path("/tmp/_shorts_v2_selftest")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    verify_dir = tmp / "verify_frames"
    verify_dir.mkdir()

    if cfg and cfg.get("clips"):
        test_cfg = json.loads(json.dumps(cfg))
    else:
        test_cfg = {
            "video_url": "https://example.com/test",
            "clips": [
                {"id": 1, "slug": "test_clip", "label": "Self Test Clip", "start": "00:00:00", "end": "00:00:02"}
            ],
            "crop": {"trim_top": 0.04, "trim_bottom": 0.10, "x_offset": 0.0},
            "audio": {},
            "fx": {"enabled": True, "show_title": True},
        }

    test_cfg.setdefault("audio", {})
    test_cfg["audio"]["source"] = "no_voice"
    test_cfg["audio"]["isolation_engine"] = "ffmpeg_vocal_cut"
    test_cfg["audio"]["bgm_path"] = ""
    validate_config(test_cfg)

    # 1. Test stereo clip with vocal suppression
    raw = tmp / "raw_stereo.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=2.0",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(raw),
    ])

    out_mp4 = tmp / "clip_01_test.mp4"
    res = render_clip(
        test_cfg["clips"][0], raw, out_mp4, verify_dir,
        test_cfg, format_font_arg(find_font()), generate_open_sfx(tmp), tmp
    )
    assert res["status"] == "rendered" and res["audio_engine"] == "ffmpeg_vocal_cut" and res["duration_s"] >= 1.8
    assert out_mp4.with_suffix(".txt").exists()
    assert (verify_dir / f"clip_{test_cfg['clips'][0]['id']:02d}.jpg").exists()

    # 2. Test video-only (silent source) handling
    raw_silent = tmp / "raw_silent.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=1.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw_silent),
    ])
    out_silent = tmp / "clip_silent_test.mp4"
    res_silent = render_clip(
        test_cfg["clips"][0], raw_silent, out_silent, verify_dir,
        test_cfg, format_font_arg(find_font()), generate_open_sfx(tmp), tmp
    )
    assert res_silent["status"] == "rendered" and res_silent["duration_s"] >= 1.2

    shutil.rmtree(tmp, ignore_errors=True)
    print("SELF-TEST PASSED: shorts_clipper v2.0 vocal suppression, silent handling, thumbnails, and metadata verified!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hardened Batch Shorts Clipper v2.0 (Multi-Clip Only)")
    parser.add_argument("--check", action="store_true", help="Print installed tools and audio-isolation engines")
    parser.add_argument("--config", default=None, help="Path to JSON job configuration")
    parser.add_argument("--clips", type=int, nargs="+", default=None, help="Render only specific clip IDs")
    parser.add_argument("--audio-source", choices=list(SOURCES), default=None, help="Override audio.source for every clip")
    parser.add_argument(
        "--isolation-engine", "--engine",
        choices=["auto", "audio_separator", "demucs", "ffmpeg_vocal_cut"],
        default=None,
        help="Override audio isolation engine",
    )
    parser.add_argument(
        "--vocal-cut-strength",
        choices=["moderate", "aggressive"],
        default=None,
        help="Override vocal suppression strength for ffmpeg_vocal_cut",
    )
    parser.add_argument("--bgm", default=None, help="Override background music track (.mp3/.wav)")
    parser.add_argument("--cookies", default=None, help="Browser name (e.g. firefox) or path to cookies.txt")
    parser.add_argument("--trim-top", type=float, default=None, help="Override crop trim_top")
    parser.add_argument("--trim-bottom", type=float, default=None, help="Override crop trim_bottom")
    parser.add_argument("--x-offset", type=float, default=None, help="Override crop x_offset")
    parser.add_argument("--no-fx", action="store_true", help="Disable visual FX and opening SFX")
    parser.add_argument("--no-title", action="store_true", help="Disable top title banner")
    parser.add_argument("--retries", type=int, default=3, help="Download retries per clip (default: 3)")
    parser.add_argument("--max-height", type=int, default=None, choices=[720, 1080, 1440, 2160], help="Max download height (default: config download.max_height, else 1440)")
    parser.add_argument("--force", action="store_true", help="Re-render clips even if output already exists")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary raw downloads")
    parser.add_argument("--self-test", action="store_true", help="Run offline validation & FFmpeg self-test")
    args = parser.parse_args()

    if args.check:
        print(json.dumps(check_environment(), indent=2))
        return

    if args.self_test:
        cfg = None
        if args.config:
            try:
                cfg = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[warn] Could not load '{args.config}' for self-test ({exc}); using built-in config.")
        run_self_test(cfg)
        return

    if not args.config:
        sys.exit("Error: --config <job.json> is required (or pass --check or --self-test).")

    cfg = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    if args.audio_source:
        cfg.setdefault("audio", {})["source"] = args.audio_source
    if args.isolation_engine:
        cfg.setdefault("audio", {})["isolation_engine"] = args.isolation_engine
    if args.vocal_cut_strength:
        cfg.setdefault("audio", {})["vocal_cut_strength"] = args.vocal_cut_strength
    if args.bgm is not None:
        cfg.setdefault("audio", {})["bgm_path"] = args.bgm
    if args.max_height is not None:
        cfg.setdefault("download", {})["max_height"] = args.max_height
    if args.trim_top is not None:
        cfg.setdefault("crop", {})["trim_top"] = args.trim_top
    if args.trim_bottom is not None:
        cfg.setdefault("crop", {})["trim_bottom"] = args.trim_bottom
    if args.x_offset is not None:
        cfg.setdefault("crop", {})["x_offset"] = args.x_offset
    if args.no_fx:
        cfg.setdefault("fx", {})["enabled"] = False
    if args.no_title:
        cfg.setdefault("fx", {})["show_title"] = False

    validate_config(cfg)

    env = check_environment()
    for warn in env["warnings"]:
        print(f"[warn] {warn}")
    for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"Error: '{tool}' not found in PATH.")

    clips = cfg["clips"]
    if args.clips:
        clips = [c for c in clips if c["id"] in args.clips]
        if not clips:
            sys.exit("Error: No matching clip IDs in config.")

    out_dir = pathlib.Path(cfg.get("output_dir", "output_clips"))
    out_dir.mkdir(parents=True, exist_ok=True)
    verify_dir = out_dir / "verify_frames"
    verify_dir.mkdir(exist_ok=True)
    work_dir = out_dir / "_tmp"
    work_dir.mkdir(exist_ok=True)

    font_arg = format_font_arg(find_font())
    sfx_path = generate_open_sfx(work_dir) if cfg["fx"].get("enabled", True) else None
    cookies = args.cookies or cfg.get("cookies_file") or cfg.get("cookies_browser") or None

    report_path = out_dir / "run_report.json"
    prev_report_map: dict[int, dict[str, Any]] = {}
    if report_path.is_file():
        try:
            prev_data = json.loads(report_path.read_text(encoding="utf-8"))
            for r in prev_data.get("results", []):
                if isinstance(r, dict) and "id" in r:
                    prev_report_map[r["id"]] = r
        except Exception:
            pass

    eng = cfg["audio"].get("isolation_engine", "auto")
    if eng == "auto":
        eng = "demucs" if env.get("demucs") else ("audio_separator" if env.get("audio_separator") else "ffmpeg_vocal_cut")

    def clip_cfg(clip: dict[str, Any]) -> dict[str, Any]:
        """The job config with this clip's own audio settings layered on top."""
        if not clip.get("audio"):
            return cfg
        c = dict(cfg)
        c["audio"] = {**cfg["audio"], **clip["audio"]}
        return c

    def engine_tag(c: dict[str, Any]) -> str:
        src = c["audio"]["source"]
        return eng if src == "no_voice" else (f"voice_only/{eng}" if src == "voice_only" else src)

    results: list[dict[str, Any]] = []
    for idx, clip in enumerate(clips, start=1):
        out_path = out_dir / f"clip_{clip['id']:02d}_{clip['slug']}.mp4"
        print(f"\n[{idx}/{len(clips)}] Clip {clip['id']:02d}: {clip['label']} ({clip['start']} - {clip['end']})")

        ccfg = clip_cfg(clip)
        req_engine = engine_tag(ccfg)
        existing_dur, _ = probe_media(out_path)
        prev_entry = prev_report_map.get(clip["id"])
        prev_engine = prev_entry.get("audio_engine") if prev_entry else None

        if not args.force and existing_dur > 1.0:
            if prev_entry and prev_entry.get("status") == "rendered" and prev_engine == req_engine:
                print(f"  -> Skipping (already rendered with {req_engine}: {out_path.name}, {existing_dur:.1f}s). Use --force to overwrite.")
                results.append(prev_entry)
                continue
            else:
                reason = f"upgrading from {prev_engine}" if prev_engine else "outdated audio"
                print(f"  -> Re-rendering clip {clip['id']:02d} ({reason} -> {req_engine}).")

        try:
            raw_path = download_segment(cfg["video_url"], clip, work_dir, cookies, args.retries, int(cfg["download"]["max_height"]))
            res = render_clip(clip, raw_path, out_path, verify_dir, ccfg, font_arg, sfx_path, work_dir)
            results.append(res)
            print(f"  -> OK: {res['file']} ({res['duration_s']}s, {res['size_mb']} MB, audio={res['audio_engine']})")
        except Exception as exc:
            print(f"  -> FAILED clip {clip['id']:02d}: {exc}", file=sys.stderr)
            results.append({"id": clip["id"], "file": out_path.name, "status": "failed", "error": str(exc)})

        # Save report incrementally after each clip
        report_path.write_text(json.dumps({"video_url": cfg["video_url"], "results": results}, indent=2), encoding="utf-8")

    report_path = out_dir / "run_report.json"
    report_path.write_text(json.dumps({"video_url": cfg["video_url"], "results": results}, indent=2), encoding="utf-8")

    if not args.keep_temp:
        shutil.rmtree(work_dir, ignore_errors=True)

    ok = sum(1 for r in results if r["status"] in ("rendered", "skipped"))
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nBatch complete: {ok}/{len(results)} succeeded, {failed} failed. Report: {report_path.resolve()}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
