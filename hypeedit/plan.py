"""Edit plan: the per-clip input to hypeedit, written in the shared vocabulary.

The vocabulary (beat kinds, text slots, what each means for any game or
content type) is defined once in .claude/skills/hype-edit/references/vocabulary.md.
This module only parses and validates it.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

FRAME_W, FRAME_H = 1080, 1920

POINT_KINDS = {"payoff", "hit", "whip"}
SPAN_KINDS = {"build", "lull"}
BEAT_KINDS = POINT_KINDS | SPAN_KINDS


@dataclass
class Beat:
    kind: str
    t: float  # source seconds
    end: float | None = None  # spans only
    focus: tuple[float, float] | None = None  # output px on the 1080x1920 frame
    lock: bool = False  # payoff: draw target brackets on the focus
    hurt: bool = False  # hit: the player takes the damage
    note: str = ""


@dataclass
class Text:
    hook: list[str]
    stamp: str
    tease: str | None = None
    outro: list[str] | None = None
    accent: str = "#ff3030"


@dataclass
class Plan:
    name: str
    source: pathlib.Path
    music: pathlib.Path | None
    music_drop: float | None
    style: str
    text: Text
    beats: list[Beat]
    out_dir: pathlib.Path
    mix_gain_db: float = 0.0
    path: pathlib.Path = field(default_factory=pathlib.Path)

    @property
    def payoff(self) -> Beat:
        return next(b for b in self.beats if b.kind == "payoff")

    @property
    def proxy(self) -> pathlib.Path:
        return proxy_of(self.source)

    @property
    def preview_media(self) -> pathlib.Path:
        """What build and the Studio preview play: the proxy when there is one."""
        return self.proxy if self.proxy.exists() else self.source

    def of_kind(self, kind: str) -> list[Beat]:
        return sorted((b for b in self.beats if b.kind == kind), key=lambda b: b.t)


def proxy_of(master: pathlib.Path) -> pathlib.Path:
    return master.with_name(f"{master.stem}_proxy{master.suffix}")


class PlanError(ValueError):
    pass


def _resolve(base: pathlib.Path, p: str | None) -> pathlib.Path | None:
    if not p:
        return None
    q = pathlib.Path(p).expanduser()
    return q if q.is_absolute() else (base / q).resolve()


def load(path: str | pathlib.Path, source_duration: float | None = None) -> Plan:
    path = pathlib.Path(path).resolve()
    raw = json.loads(path.read_text())
    base = path.parent
    errors: list[str] = []

    name = raw.get("name") or path.stem.replace(".plan", "")
    source = _resolve(base, raw.get("source"))
    if not source or not (source.exists() or proxy_of(source).exists()):
        errors.append(f"source not found: {raw.get('source')!r} or its proxy (run `python3 -m hypeedit prep` first)")

    music_raw = raw.get("music") or {}
    if isinstance(music_raw, str):
        music_raw = {"file": music_raw}
    music = _resolve(base, music_raw.get("file"))
    if music and not music.exists():
        errors.append(f"music not found: {music}")

    t = raw.get("text") or {}
    hook = t.get("hook") or []
    if isinstance(hook, str):
        hook = [hook]
    outro = t.get("outro")
    if isinstance(outro, str):
        outro = [outro]
    text = Text(
        hook=[str(x) for x in hook],
        stamp=str(t.get("stamp") or ""),
        tease=t.get("tease") or None,
        outro=[str(x) for x in outro] if outro else None,
        accent=t.get("accent") or "#ff3030",
    )
    if not 1 <= len(text.hook) <= 2:
        errors.append("text.hook needs 1 or 2 lines (line 2 is the accent line)")
    if not text.stamp:
        errors.append("text.stamp is required: the word slammed on the payoff")
    elif len(text.stamp.split()) > 2:
        errors.append(f"text.stamp {text.stamp!r} is over 2 words")
    for line in text.hook + (text.outro or []):
        if len(line.split()) > 3:
            errors.append(f"text line {line!r} is over 3 words: cut words, never shrink")

    beats: list[Beat] = []
    for i, b in enumerate(raw.get("beats") or []):
        kind = b.get("kind")
        if kind not in BEAT_KINDS:
            errors.append(f"beats[{i}]: kind {kind!r} is not one of {sorted(BEAT_KINDS)}")
            continue
        try:
            beat = Beat(
                kind=kind,
                t=float(b["t"]),
                end=float(b["end"]) if b.get("end") is not None else None,
                focus=tuple(float(v) for v in b["focus"]) if b.get("focus") else None,
                lock=bool(b.get("lock", False)),
                hurt=bool(b.get("hurt", False)),
                note=str(b.get("note", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"beats[{i}]: {exc}")
            continue
        if kind in SPAN_KINDS and (beat.end is None or beat.end <= beat.t):
            errors.append(f"beats[{i}] {kind}: a span needs end > t")
        if beat.focus and not (0 <= beat.focus[0] <= FRAME_W and 0 <= beat.focus[1] <= FRAME_H):
            errors.append(f"beats[{i}]: focus {beat.focus} is outside the 1080x1920 frame")
        if source_duration is not None and not 0 <= beat.t < source_duration:
            errors.append(f"beats[{i}]: t={beat.t} is outside the source (0-{source_duration:.2f}s)")
        beats.append(beat)

    payoffs = [b for b in beats if b.kind == "payoff"]
    if len(payoffs) != 1:
        errors.append(f"exactly one payoff beat is required, found {len(payoffs)}")

    if errors:
        raise PlanError(f"{path}:\n  - " + "\n  - ".join(errors))

    out_dir = _resolve(base, raw.get("out_dir")) or (base / name)
    return Plan(
        name=name,
        source=source,
        music=music,
        music_drop=float(music_raw["drop"]) if music_raw.get("drop") is not None else None,
        style=raw.get("style") or "phonk-hype",
        text=text,
        beats=sorted(beats, key=lambda b: b.t),
        out_dir=out_dir,
        mix_gain_db=float(raw.get("mix_gain_db", 0.0)),
        path=path,
    )
