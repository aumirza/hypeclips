# Jobs

One JSON file per source video. The pipeline reads it and writes everything to
`workspace/<name>/`.

```json
{
  "name": "carry_gta6",
  "video_url": "https://www.youtube.com/watch?v=...",
  "default_hashtags": "#GTA6 #GamingShorts",
  "cookies_browser": "",
  "crop": { "trim_top": 0.04, "trim_bottom": 0.10, "x_offset": 0 },
  "download": { "max_height": 1440 },
  "audio": { "mode": "gunshots", "isolation_engine": "demucs" },
  "fx": { "enabled": true, "show_title": true },
  "edit": { "enabled": true, "style": "phonk-hype", "music": "assets/music/phonk.mp3", "accent": "#ff3030" },
  "clips": [
    {
      "id": 1,
      "slug": "clean_headshot",
      "label": "Clean Headshot",
      "start": "00:44:08",
      "end": "00:44:22",
      "title": "Insanely Clean Headshot in GTA 6!",
      "caption": "That headshot physics hit different in GTA 6."
    }
  ]
}
```

- `clips[].start` / `end`: timestamps in the source video (`HH:MM:SS` or `MM:SS`), 1–180 s apart.
- `title` / `caption` / hashtags become the post text (`final/<clip>.txt`); `title` also seeds the hype-edit text.
- `crop` cuts the 9:16 window out of the stream layout; `x_offset` shifts it (−0.4..0.4).
- `audio.mode`: `gunshots` (strip the streamer's voice, keep game sound), `bgm`, or `original`.
- `edit`: the hype edit on top of the plain short. `"edit": false` on a clip skips it for that clip.
- Everything else the clipper supports (TTS, bgm volume, sfx) is listed in `pipeline/clipper.py`.
