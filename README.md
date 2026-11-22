# hypeclips

Give it a stream URL; get finished vertical YouTube shorts with sound and visual effects, rendered with [HyperFrames](https://hyperframes.heygen.com).

- **Ask for something** ("gunfight shorts", "top 5 car stunts ranking") and it finds matching moments; **ask for nothing** and it recommends what the stream is good for.
- Every proposal comes back as **timestamps with preview links and 360p verify sheets for you to confirm** before anything is made.
- A short is **one clip** (single), **2-3 clips** (montage) or a **countdown** (ranking, #N to #1).
- Gameplay clips get the `phonk-hype` edit (speed ramps, slow-mo payoff, kill-cam, punch-ins, shake, flash, stamp, music drop); reaction and funny clips get the `talk` edit (voice kept, punch-in on the punchline, quiet bed). Montages and rankings add the title or header, cuts, rank slams, one music bed and an outro question.
- Any game or content, any caption language (non-Latin captions are romanized for reading); nothing is GTA-specific.

Built to be driven by an AI agent (Claude Code): it reads the stream's captions and signals, picks and verifies moments, writes each clip's edit plan from the frames, reviews, and renders. The `clip-pipeline` and `hype-edit` skills in `.claude/skills/` carry the workflow and the style.

## Setup

- `ffmpeg`, Node.js (for `npx hyperframes`), [uv](https://docs.astral.sh/uv/)
- `uv venv .venv && uv pip install --python .venv/bin/python yt-dlp demucs`
- a music track in `assets/music/` (see `assets/music/README.md`)
- `python3 -m pipeline doctor` checks all of it

## Use

```bash
python3 -m pipeline research jobs/carry_gta6_research.json  # URL -> clips (resumable; AI gates: picks, selection)
python3 -m pipeline run    jobs/carry_gta6.json   # shorts, edit sources, look sheets, plan drafts, builds
python3 -m pipeline status jobs/carry_gta6.json   # stage table + what is next
python3 -m pipeline look   jobs/carry_gta6.json --clip 3 --detail 5.2,6.1
python3 -m pipeline render jobs/carry_gta6.json   # final renders -> workspace/carry_gta6/final/
```

Every command is resumable: each stage checks its own outputs and redoes only what is missing or stale. The editorial gates: picks, selection and **your confirmation** (research), a `plan.json` per clip, and a review of each build's snapshot sheet.

## Pipeline

| stage | what | output in `workspace/<job>/` |
| --- | --- | --- |
| research | captions (romanized if needed), comment/chat/heatmap/loudness signals, hot windows, AI picks, 360p verify sheets, AI selection; writes `clips` into the job | `research/` |
| cut | download at `download.max_height` (1440p), 9:16 crop, voice separation per clip, plain cut | `shorts/` |
| proxy | 540×960 edit source | `edits/<clip>/source_proxy.mp4` |
| look | timestamped contact sheet + audio envelope | `edits/<clip>/look/` |
| draft | plan template | `edits/<clip>/plan.draft.json` |
| master | 1080×1920 sharpened edit source | `edits/<clip>/source.mp4` |
| build | plan → HyperFrames project, check, snapshot sheet | `edits/<clip>/project/` |
| render | each clip's edit (a whole short, or a segment of one) | `renders/<clip>.mp4` |
| short | single: the clip's render; montage/ranking: segments composed with cuts, rank slams, music bed, outro; loudness check, post text | `final/<short>.mp4`, `.txt` |

## Layout

```
jobs/            job configs (one per source video)
pipeline/        entry point; clipper.py is the download/crop/audio engine
hypeedit/        edit library: plan vocabulary -> moves -> HyperFrames HTML
assets/music/    local music (git-ignored)
.claude/skills/  clip-pipeline (workflow), hype-edit (plans, style, vocabulary)
workspace/       all generated files (git-ignored)
```
