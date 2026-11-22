# Architecture

## Goal

Stream URL in, finished vertical YouTube shorts out. The person says what they want (`research.request`: "gunshot shorts", "top 5 car stunts ranking") or nothing (the tool recommends), confirms the proposed timestamps, and gets shorts with sound and visual effects. A **short** is 1 clip (single), 2-3 clips (montage) or a countdown (ranking, #N to #1). An AI agent (Claude Code) drives it through `python3 -m pipeline`; the skills in `.claude/skills/` carry the workflow and the taste.

## Flow

```
URL + brief + request
  │ research    captions, comment timestamps, chat, most-replayed, speaker loudness
  │             → hot windows (chunks/wNN.md) → AI picks (gate 1)
  │             → shortlist + 360p verify sheets → AI proposes shorts (gate 2)
  │             → proposal.md → PERSON CONFIRMS (gate 3) → clips + shorts written into the job
  │ run         per clip: 1440p download, crop, voice separation, plain cut,
  │             proxy, look sheets, plan draft → AI writes plan.json (gate 4)
  │             → master, build (HyperFrames project), check, snap → AI reviews (gate 5)
  │ render      per clip: edit → renders/<clip>.mp4
  │             per short: single = its clip's render; montage/ranking = shortcompose
  ▼             → final/short_NN_slug.mp4 + .txt (title, caption, hashtags)
```

Every command is resumable: each stage checks its own outputs and redoes only what is missing or stale. The gates are where judgment goes; everything else is mechanical.

## Pieces

| path | role |
| --- | --- |
| `pipeline/__main__.py` | CLI: `doctor`, `research`, `run`, `status`, `look`, `render` |
| `pipeline/job.py` | job model: `Clip`, `Short`, every workspace path |
| `pipeline/stages.py` | stage functions (cut, proxy, look, draft, master, build, render, make_short) |
| `pipeline/clipper.py` | download (yt-dlp sections), crop, voice separation (demucs / audio-separator / ffmpeg cut), plain cut |
| `pipeline/research/` | `fetch` (yt-dlp), `text` (captions, romanize), `signals` (timeline), `windows` (chunks), `select` (shortlist, verify, proposal, finalize), `run` (orchestration and gates), `audioscan` (numpy loudness, run in .venv) |
| `hypeedit/` | the edit library: `plan` (vocabulary), `timing` (speed ramp), `moves` (effects), `style` (phonk-hype, talk), `project` (HyperFrames HTML), `shortcompose` (montage/ranking), `media` (ffmpeg helpers, prep, look, drop finder) |
| `hypeedit/assets/sfx/` | 6 Pixabay sounds with measured peaks |
| `workspace/<job>/` | everything generated (git-ignored); layout in `pipeline/job.py`'s docstring |

## Data model (job JSON)

- `clips[]`: a time range in the stream plus `audio.source` (original, no_voice, voice_only, muted), `style` (phonk-hype, talk), `hint` (kind, payoff, hook from research).
- `shorts[]`: `format` + clip ids in play order (+ header, hook, outro, post text). No `shorts` = each clip is its own single. A clip belongs to one short; clips inside a montage or ranking are edited in `segment` mode (no hook, outro or music of their own).
- `research`: brief, request, signals, kinds (length, audio, style per kind), segment lengths. Defaults in `pipeline/research/config.py`.

## Key mechanisms

- **Time.** Plans are in *source seconds* of the clip and *output pixels* (1080×1920). A speed ramp is a HyperFrames `rate` lane; `hypeedit/timing.py` maps source to output time exactly, and every effect is placed in output time.
- **Proxy and master.** Sheets, builds and previews use a 540×960 proxy; only render switches the video to the 1080×1920 master (separate filenames so HyperFrames' caches never mix them).
- **Sound.** Each sound is placed so its measured peak lands one frame after its picture event. The music drop is found per short (`media.pick_drop`: the bar that comes in hardest after a quieter stretch) and lined up with the payoff or #1.
- **Raw downloads** are stamped with `max_height|start|end`; a changed range or height re-fetches and clears derived audio and stems.
