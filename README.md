# hypeclips

Turn timestamps from a long gameplay stream into vertical shorts, then into **hype edits**: speed ramps, slow-mo on the payoff, punch-ins, shake, flashes, stamp text, sound effects and a music drop timed to the payoff, rendered with [HyperFrames](https://hyperframes.heygen.com).

This project only makes clips: one finished short per timestamp range. Combining clips (rankings, compilations) is a separate project that consumes `workspace/<job>/final/`.

Built to be driven by an AI agent (Claude Code): you write the job, the agent runs the pipeline, writes an edit plan per clip from the frames, reviews, and renders.

## Setup

- `ffmpeg`, Node.js (for `npx hyperframes`), [uv](https://docs.astral.sh/uv/)
- `uv venv .venv && uv pip install --python .venv/bin/python yt-dlp demucs`
- a music track in `assets/music/` (see `assets/music/README.md`)
- `python3 -m pipeline doctor` checks all of it

## Use

```bash
python3 -m pipeline run    jobs/carry_gta6.json   # shorts, edit sources, look sheets, plan drafts, builds
python3 -m pipeline status jobs/carry_gta6.json   # stage table + what is next
python3 -m pipeline look   jobs/carry_gta6.json --clip 3 --detail 5.2,6.1
python3 -m pipeline render jobs/carry_gta6.json   # final renders -> workspace/carry_gta6/final/
```

`run` is resumable: each stage checks its own outputs and redoes only what is missing or stale. Between `run` and `render` sit two editorial gates: a `plan.json` per clip (written from `plan.draft.json` after reading the clip's frames) and a review of each build's snapshot sheet. With Claude Code, ask it to process a job; the `clip-pipeline` and `hype-edit` skills in `.claude/skills/` carry the workflow and the style.

## Pipeline

| stage | what | output in `workspace/<job>/` |
| --- | --- | --- |
| short | download at `download.max_height` (1440p), 9:16 crop, demucs strips the streamer's voice, plain short | `shorts/` |
| proxy | 540×960 edit source | `edits/<clip>/source_proxy.mp4` |
| look | timestamped contact sheet + audio envelope | `edits/<clip>/look/` |
| draft | plan template | `edits/<clip>/plan.draft.json` |
| master | 1080×1920 sharpened edit source | `edits/<clip>/source.mp4` |
| build | plan → HyperFrames project, check, snapshot sheet | `edits/<clip>/project/` |
| render | master render, loudness check, post text | `final/<clip>.mp4`, `.txt` |

## Layout

```
jobs/            job configs (one per source video)
pipeline/        entry point; clipper.py is the download/crop/audio engine
hypeedit/        edit library: plan vocabulary -> moves -> HyperFrames HTML
assets/music/    local music (git-ignored)
.claude/skills/  clip-pipeline (workflow), hype-edit (plans, style, vocabulary)
workspace/       all generated files (git-ignored)
```
