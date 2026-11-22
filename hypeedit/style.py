"""Styles: the taste, as numbers. A style decides how hard each move hits.

phonk-hype is the clip_03 pilot (see hypeedit/examples/clip03.plan.json), with the zoom
capped lower and grain cut after the blur review. Add a style by copying the
dict and changing numbers; moves.py reads only these keys.
"""

PHONK_HYPE = {
    # speed ramp (rates are playback speed; output seconds unless noted)
    "build_rate": 1.7,  # tension stretch plays fast
    "lull_rate": 1.35,  # dead stretch after the payoff
    "slow_rate": 0.22,  # payoff slow-mo
    "slow_lead": 0.5,  # output seconds of slow-mo before the payoff frame
    "slow_tail": 1.1,  # output seconds of slow-mo after it
    "ramp_transition": 0.25,  # each speed change eases over this long
    # camera
    "punch": 1.3,  # payoff zoom onto the focus (kept low: sources are upscaled crops)
    "punch_kick": 1.1,  # extra snap on the payoff frame, times punch
    "punch_settle": 1.04,  # where the zoom rests during the slow-mo, times punch
    "hit_punch": 1.12,  # quick zoom for a cluster of hits
    "hit_cluster": 1.0,  # hits closer than this (output s) share one punch
    "jolt_payoff": (30, 0.45),  # shake amplitude px, duration s
    "jolt_hit": (14, 0.2),
    "jolt_hurt": (24, 0.35),
    # grade (npx hyperframes media-treatment payload) and its punches
    "grade": {
        "preset": "deep-contrast",
        "intensity": 0.85,
        "adjust": {"saturation": 0.18, "vibrance": 0.15, "temperature": 0.04},
        "details": {"vignette": 0.32, "grain": 0.04, "grainSize": 0.15},
    },
    "flash_exposure": 0.8,
    "flash_bloom": 1.6,
    "hurt_exposure": -0.45,
    # mix: levels measured to land near -14.5 LUFS on the pilot
    "levels": {
        "game": 0.74,
        "game_slowmo": 0.3,  # times game, while the slow-mo stretches the audio
        "music": 0.265,
        "music_lane": {"base": 0.8, "dip": 0.45, "drop": 1.1},
        "whoosh": 0.25,
        "riser": 0.085,
        "boom": 0.265,
        "glitch_stamp": 0.117,
        "glitch_hurt": 0.064,
    },
    "text": {
        "display_font": "Archivo Black",
        "tease_font": "Oswald",
        "hook_sizes": (66, 118),  # line 1, accent line 2
        "stamp_size": 114,
        "outro_sizes": (96, 100),
        "max_text_width": 800,  # px; keeps clear of the Shorts/TikTok action rail
    },
    "outro_hold": 2.2,
    # which payoff moves this style uses, and how long the moment is held after the payoff frame
    "payoff_moves": {"letterbox", "punch", "lock", "flash", "jolt", "stamp", "riser", "boom", "glitch"},
    "hold_after": 0.0,  # 0 = until the slow-mo ends
}

# talk: for reactions, funny bits, hot takes. The voice is the point, so no slow-mo or
# kill-cam; a gentle punch-in and a soft hit on the punchline, a quiet music bed under the voice.
TALK = {
    **PHONK_HYPE,
    "build_rate": 1.0,
    "lull_rate": 1.15,
    "slow_rate": 1.0,
    "punch": 1.12,
    "punch_kick": 1.04,
    "punch_settle": 1.0,
    "jolt_payoff": (10, 0.25),
    "grade": {
        "preset": "deep-contrast",
        "intensity": 0.6,
        "adjust": {"saturation": 0.12, "vibrance": 0.1},
        "details": {"vignette": 0.25, "grain": 0.03, "grainSize": 0.15},
    },
    "levels": {
        **PHONK_HYPE["levels"],
        "game": 0.9,  # the voice
        "game_slowmo": 1.0,
        "music": 0.09,
        "music_lane": {"base": 1.0, "dip": 0.8, "drop": 1.25},
        "boom": 0.16,
        "whoosh": 0.18,
    },
    "payoff_moves": {"punch", "jolt", "stamp", "boom"},
    "hold_after": 1.6,
}

STYLES = {"phonk-hype": PHONK_HYPE, "talk": TALK}


def get(name: str) -> dict:
    try:
        return STYLES[name]
    except KeyError:
        raise SystemExit(f"unknown style {name!r}; known: {', '.join(STYLES)}") from None
