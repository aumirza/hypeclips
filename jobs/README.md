# Jobs

One JSON file per source video. Everything generated goes to `workspace/<name>/`.

## Start from a URL (research finds the clips)

The smallest job: a URL, a brief, and an empty `clips` list. `python3 -m pipeline research jobs/<name>.json` fills `clips`.

```json
{
  "name": "my_stream",
  "video_url": "https://www.youtube.com/watch?v=...",
  "edit": { "music": "assets/music/phonk.mp3" },
  "research": {
    "brief": "Rocket League tournament stream by X, English commentary. Want insane goals, saves and the best rage moments.",
    "count": 8,
    "hashtags": ["#RocketLeague"]
  },
  "clips": []
}
```

### `research` (all optional except `brief`, which the picker reads first)

| key | default | meaning |
| --- | --- | --- |
| `brief` | `""` | what the stream is, who, which language, what clips you want |
| `count` / `min_score` | `8` / `7` | clips wanted; picks below the score are dropped (never quietly lowered) |
| `captions` | `["en", "orig"]` | caption tracks in order; `orig` = the stream's own language (auto-translated tracks are often rate-limited) |
| `romanize` | `true` | non-Latin captions to Latin letters (3-4x fewer tokens to read) |
| `signals` | all on | `comments` (timestamps in comments, likes-weighted), `chat` (replay chat), `heatmap` (most replayed), `audio` (speaker loudness), `max_comments` |
| `weights` | see `pipeline/research/config.py` | how much each signal counts when choosing what to read |
| `scan` | `"hot"` | `hot`: read only the strongest signal windows; `full`: read the whole stream in `chunk_min` chunks |
| `windows`, `window_sec` | `max(12, 2 x count)`, `240` | how many hot windows, how long each |
| `kinds` | action, fail, reaction, funny, hot_take | per kind: `length` [min, max] s, `audio` (below), `edit` (hype edit or plain short), `means` (shown to the picker) |
| `max_per_kind` | none | variety cap in the shortlist |
| `verify` | `true` | 360p contact sheet per shortlisted moment |
| `output_language` | `"en"` | language of hooks, titles and captions |
| `hashtags` | `[]` | added to every clip |

Gameplay kinds default to `audio: no_voice` + hype edit; talk kinds to `audio: original` + plain short.

## Or give the timestamps yourself

```json
"clips": [
  {
    "id": 1, "slug": "clean_headshot", "label": "Clean Headshot",
    "start": "00:44:08", "end": "00:44:22",
    "title": "Insanely clean headshot", "caption": "That headshot physics hit different.",
    "audio": { "source": "no_voice" },
    "edit": true,
    "hint": { "kind": "action", "payoff": "00:44:13.6" }
  }
]
```

- `start` / `end`: `HH:MM:SS(.s)` or `MM:SS`, 1-180 s apart. `title` / `caption` / `hashtags` become the post text.
- `audio`, `edit`, `hint` are optional per clip; `hint.payoff` (stream time) points the edit plan at the moment.

## Shared sections

- `audio.source`: what is kept of the stream's own sound: `original`, `no_voice` (voice removed, game/world sound kept), `voice_only`, or `muted`. `audio.on_fail` when voice separation is unavailable: `ffmpeg_cut` (weaker built-in cut, default), `original`, or `error`. Old `audio.mode` values still work (`gunshots` = `no_voice`, `bgm` = `muted`).
- `crop`: the 9:16 window cut from the stream (`trim_top`, `trim_bottom`, `x_offset` -0.4..0.4).
- `download.max_height`: 720, 1080, 1440 (default) or 2160.
- `edit`: the hype edit (`enabled`, `style`, `music`, `accent`).
- `cookies_browser` / `cookies_file`: for members-only or age-restricted videos.
- Everything else the clipper supports (TTS, bgm volume, sfx) is listed in `pipeline/clipper.py`.
