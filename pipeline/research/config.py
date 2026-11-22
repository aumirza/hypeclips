"""The `research` section of a job: defaults, merged with what the job sets.

Everything content-specific (game, creator, language, what counts as a good
moment) comes from here, never from code.
"""

from __future__ import annotations

import copy

DEFAULTS = {
    # free text the picker reads first: what the stream is, who, what kind of clips you want
    "brief": "",
    "count": 8,  # clips to end up with
    "min_score": 7,  # 0-10; picks below are dropped, never quietly lowered
    # caption tracks to try in order: a language code ("en"), or "orig" (the stream's own
    # language: manual subs, else YouTube's "<lang>-orig" auto track). Auto-translated
    # tracks are often rate-limited by YouTube (429), so "orig" is the dependable fallback.
    "captions": ["en", "orig"],
    "romanize": True,  # non-Latin captions -> Latin letters (3-4x fewer tokens to read)
    # crowd and audio signals; each is skipped when the platform has none
    "signals": {
        "comments": True,  # timestamps viewers wrote in comments, weighted by likes
        "chat": True,  # chat speed-ups (YouTube replay chat)
        "heatmap": True,  # YouTube "most replayed"
        "audio": True,  # low-bitrate audio: speaker loudness (yelling, freakouts)
        "max_comments": 2000,
    },
    # how much each signal counts in the combined score that picks hot windows
    "weights": {"comments": 1.6, "heatmap": 1.5, "chat": 1.2, "loud": 1.0, "speech": 0.4},
    "scan": "hot",  # "hot": read only the top signal windows; "full": read the whole stream
    "windows": None,  # hot windows to read (default: max(12, 2 x count))
    "window_sec": 240,  # length of each hot window
    "chunk_min": 10,  # chunk length for scan="full"
    # moment kinds: allowed lengths, which audio the short keeps, and whether it gets a hype edit
    "kinds": {
        "action": {"length": [8, 25], "audio": "no_voice", "edit": True,
                   "means": "something happens in the game: kill, stunt, crash, clutch, chase"},
        "fail": {"length": [8, 30], "audio": "no_voice", "edit": True,
                 "means": "a plan goes wrong in the game: death, wreck, getting caught"},
        "reaction": {"length": [12, 45], "audio": "original", "edit": False,
                     "means": "the streamer's reaction is the point: freakout, disbelief, first look"},
        "funny": {"length": [10, 40], "audio": "original", "edit": False,
                  "means": "a joke, bit or chat interaction that lands without setup"},
        "hot_take": {"length": [12, 45], "audio": "original", "edit": False,
                     "means": "a strong opinion people will argue about"},
    },
    "max_per_kind": None,  # e.g. 4: variety cap per kind in the final shortlist
    "verify": True,  # 360p contact sheets of each shortlisted moment
    "output_language": "en",  # titles, hooks and captions are written in this language
    "hashtags": [],  # always added to every clip's hashtags
}


def merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "kinds":
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve(job_cfg: dict) -> dict:
    r = merge(DEFAULTS, job_cfg.get("research") or {})
    if r["scan"] not in ("hot", "full"):
        raise SystemExit(f"research.scan must be 'hot' or 'full', not {r['scan']!r}")
    for name, k in r["kinds"].items():
        lo, hi = k.get("length", [8, 45])
        if not 3 <= lo < hi <= 180:
            raise SystemExit(f"research.kinds.{name}.length must be [min, max] seconds within 3-180")
        if k.get("audio", "original") not in ("original", "no_voice", "voice_only", "muted"):
            raise SystemExit(f"research.kinds.{name}.audio must be original, no_voice, voice_only or muted")
    r["windows"] = r["windows"] or max(12, 2 * int(r["count"]))
    return r
