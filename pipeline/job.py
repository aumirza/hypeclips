"""Job config -> clips and every path the pipeline reads or writes.

A job is one JSON file in jobs/ (see jobs/README.md). All artefacts live
under workspace/<job name>/, which git ignores:

    workspace/<job>/
      job.resolved.json          config handed to the clipper
      shorts/                    plain shorts from the clipper (+ _tmp/ raw downloads, demucs stems)
      edits/clip_NN_slug/        one hype edit per clip
        source_proxy.mp4         540x960, for look/build/preview
        source.mp4               1080x1920 master, for render
        look/                    sheets for finding beats
        plan.draft.json          template written by the pipeline
        plan.json                written by the AI/editor: the gate to build
        project/                 generated HyperFrames project
      final/clip_NN_slug.mp4     rendered hype edit + .txt post metadata
"""

from __future__ import annotations

import copy
import json
import pathlib
from dataclasses import dataclass

from . import clipper

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"


@dataclass
class Clip:
    id: int
    slug: str
    label: str
    title: str
    caption: str
    start: str
    end: str
    edit: bool
    audio: str = "no_voice"  # original | no_voice | voice_only | muted
    hint: dict | None = None  # from research: kind, payoff (stream time), hook, why

    @property
    def key(self) -> str:
        return f"clip_{self.id:02d}_{self.slug}"


def audio_source(cfg: dict, clip: dict) -> str:
    """Per-clip audio.source, else the job's, else what the legacy audio.mode meant."""
    a = cfg.get("audio") or {}
    return ((clip.get("audio") or {}).get("source") or a.get("source")
            or clipper.LEGACY_MODES.get(a.get("mode", "gunshots"), "no_voice"))


class Job:
    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path).resolve()
        self.cfg = json.loads(self.path.read_text(encoding="utf-8"))
        self.name = self.cfg.get("name") or self.path.stem
        # the clipper validates (and fills defaults into) its own sections; a job that
        # only has a video_url so far (before `research` fills its clips) skips that
        self.has_clips = bool(self.cfg.get("clips"))
        if self.has_clips:
            checked = copy.deepcopy(self.cfg)
            clipper.validate_config(checked)
            self.cfg = checked
        elif not str(self.cfg.get("video_url", "")).startswith(("http://", "https://")):
            raise SystemExit(f"{self.path.name}: needs a video_url")
        e = self.cfg.get("edit") or {}
        self.edit = {"enabled": e.get("enabled", True), "style": e.get("style", "phonk-hype"),
                     "music": e.get("music"), "accent": e.get("accent", "#ff3030")}
        if self.edit["music"]:
            m = pathlib.Path(self.edit["music"])
            self.edit["music"] = m if m.is_absolute() else (ROOT / m)
            if not self.edit["music"].exists():
                raise SystemExit(f"{self.path.name}: edit.music not found: {self.edit['music']}")
        self.clips = [
            Clip(c["id"], c["slug"], c["label"], c.get("title", c["label"]), c.get("caption", ""),
                 c["start"], c["end"], bool(c.get("edit", True)) and self.edit["enabled"],
                 audio_source(self.cfg, c), c.get("hint") or {})
            for c in self.cfg.get("clips") or []
        ]
        self.ws = WORKSPACE / self.name
        self.shorts = self.ws / "shorts"
        self.tmp = self.shorts / "_tmp"
        self.edits = self.ws / "edits"
        self.final = self.ws / "final"

    def select(self, ids: list[int] | None) -> list[Clip]:
        if not ids:
            return self.clips
        chosen = [c for c in self.clips if c.id in ids]
        missing = set(ids) - {c.id for c in chosen}
        if missing:
            raise SystemExit(f"no clip ids {sorted(missing)} in {self.path.name}")
        return chosen

    # ---- clipper artefacts
    def raw(self, c: Clip) -> pathlib.Path:
        return self.tmp / f"raw_{c.id:02d}.mp4"

    def raw_is_current(self, c: Clip) -> bool:
        stamp = self.raw(c).with_name(self.raw(c).name + ".maxh")
        return self.raw(c).exists() and stamp.exists() and stamp.read_text().strip() == str(self.cfg["download"]["max_height"])

    def edit_audio(self, c: Clip) -> tuple[pathlib.Path | None, str | None]:
        """(replacement audio for the edit source, warning). None audio = keep the raw's own sound."""
        if c.audio in ("no_voice", "voice_only"):
            stem = "no_vocals" if c.audio == "no_voice" else "vocals"
            hits = sorted(self.tmp.glob(f"demucs_out/*/raw_{c.id:02d}_orig/{stem}.*")) + \
                sorted(self.tmp.glob(f"sep_raw_{c.id:02d}/*{'Instrumental' if stem == 'no_vocals' else 'Vocals'}*"))
            if hits:
                return hits[0], None
            return None, f"{c.key}: audio.source={c.audio} but no separated stem was found; the edit keeps the ORIGINAL sound"
        return None, None

    def short(self, c: Clip) -> pathlib.Path:
        return self.shorts / f"{c.key}.mp4"

    def meta(self, c: Clip) -> pathlib.Path:
        return self.shorts / f"{c.key}.txt"

    # ---- edit artefacts
    def edit_dir(self, c: Clip) -> pathlib.Path:
        return self.edits / c.key

    def master(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "source.mp4"

    def proxy(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "source_proxy.mp4"

    def look_dir(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "look"

    def plan(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "plan.json"

    def draft(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "plan.draft.json"

    def project(self, c: Clip) -> pathlib.Path:
        return self.edit_dir(c) / "project"

    def snap_sheets(self, c: Clip) -> list[pathlib.Path]:
        return sorted((self.project(c) / ".hypeedit" / "snap").glob("contact-sheet-*.jpg"))

    def final_video(self, c: Clip) -> pathlib.Path:
        return self.final / f"{c.key}.mp4"
