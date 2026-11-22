"""ffmpeg / HyperFrames CLI helpers: probing, source prep, the `look` sheets, beats."""

from __future__ import annotations

import json
import math
import pathlib
import struct
import subprocess


def run(cmd: list[str], cwd: str | pathlib.Path | None = None, capture=True) -> str:
    res = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "")[-1500:] if capture else ""
        raise SystemExit(f"command failed ({res.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return res.stdout if capture else ""


def npx_json(args: list[str], cwd=None) -> dict:
    out = run(["npx", "hyperframes", *args], cwd=cwd)
    return json.JSONDecoder().raw_decode(out[out.index("{"):])[0]


def probe(path) -> dict:
    d = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)]))
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    info = {"duration": float(d["format"]["duration"]), "has_audio": any(s["codec_type"] == "audio" for s in d["streams"])}
    if v:
        num, den = v.get("avg_frame_rate", "30/1").split("/")
        info.update(width=int(v["width"]), height=int(v["height"]), fps=float(num) / float(den or 1))
    return info


def mono_samples(path, rate=2000) -> list[float]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True,
    ).stdout
    return list(struct.unpack(f"{len(raw) // 4}f", raw))


# ---------------------------------------------------------------- prep


def proxy_path(master) -> pathlib.Path:
    m = pathlib.Path(master)
    return m.with_name(f"{m.stem}_proxy{m.suffix}")


def prep(src, out, audio=None, trim_top=0.04, trim_bottom=0.10, x_offset=0.0, sharpen=0.6, fps_cap=60, master=True):
    """Raw footage -> a fast 540x960 proxy, then the high-quality 1080x1920 master.

    Same crop as pipeline/clipper.py, at the input's full resolution and fps, with
    a light luma sharpen on the master. The proxy is for look/build/snap and the
    Studio preview; `render` swaps the master in. Feed it the highest-res raw
    download you have: a 1440p input gives a 697 px crop instead of 522 px.
    """
    info = probe(src)
    w, h = info["width"], info["height"]
    vertical = abs(w / h - 9 / 16) < 0.01
    if vertical:
        crop, crop_w = [], w
    else:
        usable_h = h * (1 - trim_top - trim_bottom)
        crop_w = min(w, usable_h * 9 / 16)
        x = max(0, min(w - crop_w, (w - crop_w) / 2 + w * x_offset))
        crop = [f"crop={int(crop_w) // 2 * 2}:{int(usable_h) // 2 * 2}:{int(x)}:{int(h * trim_top)}"]
    fps = min(fps_cap, round(info.get("fps", 30)))
    has_audio = bool(audio or info["has_audio"])
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def encode(dst, size, extra_vf, x264, abr):
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
        if audio:
            cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-shortest"]
        vf = crop + [f"scale={size}:flags=lanczos"] + extra_vf + ["setsar=1"]
        cmd += ["-vf", ",".join(vf), "-r", str(fps), "-c:v", "libx264", *x264, "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-b:a", abr] if has_audio else ["-an"]
        run(cmd + [str(dst)])

    proxy = proxy_path(out)
    encode(proxy, "540:960", [], ["-crf", "26", "-preset", "veryfast"], "128k")
    if master:
        encode(out, "1080:1920", [f"unsharp=5:5:{sharpen}:5:5:0"] if sharpen > 0 else [], ["-crf", "14", "-preset", "slow"], "256k")
    return {"crop_from": f"{w}x{h}", "crop_width": int(crop_w), "fps": fps, "proxy": str(proxy), "master": str(out) if master else None}


# ---------------------------------------------------------------- look


def look(src, out_dir, detail: list[tuple[float, float]] | None = None) -> list[str]:
    """Sheets an agent reads to find beats: overview, detail strips with a focus grid, audio envelope."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    dur = info["duration"]
    made = []

    n = math.ceil(dur * 2)
    rows = math.ceil(n / 8)
    ov = out_dir / "overview.jpg"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
         "fps=2,scale=180:-2,drawtext=text='%{pts\\:flt}':x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,"
         f"tile=8x{rows}", "-frames:v", "1", str(ov)])
    made.append(str(ov))

    for a, b in detail or []:
        p = out_dir / f"detail_{a:.2f}-{b:.2f}.jpg"
        frames = math.ceil((b - a) * 10)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a}", "-t", f"{b - a}", "-i", str(src), "-vf",
             "fps=10,drawgrid=w=iw/10:h=ih/10:t=2:c=yellow@0.55,scale=270:-2,"
             f"drawtext=text='%{{pts\\:flt\\:{a}}}':x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,"
             f"tile=6x{math.ceil(frames / 6)}", "-frames:v", "1", str(p)])
        made.append(str(p))

    if info["has_audio"]:
        a = mono_samples(src)
        w = 100  # 50 ms windows at 2 kHz
        pk = [max((abs(x) for x in a[i:i + w]), default=0) for i in range(0, len(a) - w, w)]
        top = max(pk) or 1
        lines = ["# 50 ms peak envelope of the source audio, 1 s per row ( .:-=+*#%@ = quiet..loud )"]
        line = ""
        for i, p in enumerate(pk):
            line += " .:-=+*#%@"[min(9, int(p / top * 9.99))]
            if i % 20 == 19:
                lines.append(f"{(i - 19) * 0.05:6.1f}s |{line}|")
                line = ""
        env = out_dir / "audio_envelope.txt"
        env.write_text("\n".join(lines) + "\n")
        made.append(str(env))
    return made


# ---------------------------------------------------------------- music


def pick_drop(music, payoff_out: float, dur_out: float) -> tuple[float, str]:
    """The bar where the track comes in hardest after a quieter stretch, placed on the payoff."""
    d = npx_json(["beats", str(music), "--json"])
    beats = d["beatTimes"]
    total = probe(music)["duration"]
    a = mono_samples(music)
    bars = []
    for i in range(0, len(beats) - 4, 4):
        s, e = int(beats[i] * 2000), int(beats[i + 4] * 2000)
        seg = a[s:e] or [0.0]
        bars.append((beats[i], math.sqrt(sum(x * x for x in seg) / len(seg))))
    loud = max(r for _, r in bars) if bars else 0
    best = None
    for i in range(4, len(bars)):
        t, r = bars[i]
        if r < 0.85 * loud:
            continue
        before = sum(x for _, x in bars[i - 4:i]) / 4
        score = r / max(before, 1e-6)
        start = t - payoff_out
        if start < 0 or start + dur_out > total:
            continue
        if best is None or score > best[0]:
            best = (score, t)
    if best:
        return best[1], f"drop at {best[1]:.2f}s ({best[0]:.1f}x the 4 bars before, {d.get('bpm')} bpm)"
    return max(0.0, min(payoff_out, total - dur_out)), "no clear drop that fits; track starts at its top"


def file_peak(path) -> float:
    """Seconds from file start to the sound's peak (for sfx not in the known table)."""
    d = npx_json(["audio", str(path), "--json"])
    return float(d["items"][0]["moments"]["peak"])
