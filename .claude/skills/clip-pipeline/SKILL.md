---
name: clip-pipeline
description: Run the clips pipeline end to end, from a stream URL (research finds the moments) or a job config of timestamps to rendered shorts in workspace/<job>/final. Use when given a video URL, timestamps or a job config to turn into shorts, asked to find clips in a stream, or asked to resume, check or render a job.
---

# Clip pipeline

The person gives a stream URL and, optionally, what they want ("gunfight shorts", "top 5 car stunts ranking"); they get finished YouTube shorts with sound and visual effects in `workspace/<job>/final/`. A **short** uses 1 clip (single), 2-3 (montage) or a countdown of several (ranking). With no request, the tool recommends shorts; either way the person confirms the timestamps before anything is made.

One command drives the whole workflow: `python3 -m pipeline <cmd> jobs/<job>.json`, run from the repo root. Every stage checks its own outputs, so commands are safe to repeat and only do what is missing or stale. Job format: [jobs/README.md](../../../jobs/README.md). Layout of `workspace/<job>/`: the docstring of `pipeline/job.py`.

The pipeline does the mechanical work; you do the editorial work at its gates: **picks**, **selection** and the person's **confirmation** (research), **plan** (each clip's edit) and **review** (each snap sheet before rendering).

## Steps

1. **Job.** Write `jobs/<name>.json` (shapes in `jobs/README.md`): `video_url`, `research.brief` (what the stream is, who, its language), `research.request` (what the person asked for, in their words; empty when they asked for recommendations), `edit.music`, `"clips": []`. If they gave timestamps themselves, write the clips (and `shorts` when they want them combined) and skip to step 2.
   - **Research**: `python3 -m pipeline research jobs/<name>.json`, repeated until it says `research done`. Read `references/picking.md` first; it covers each gate. At `NEEDS PICKS`, read every `research/chunks/wNN.md` and write `research/picks/wNN.json` (`[]` when nothing qualifies). At `NEEDS SELECTION`, look at every `research/verify/<id>.jpg` and propose shorts in `research/selection.json`. At `NEEDS CONFIRMATION`, show the person `research/proposal.md` (each short: its clips in order with timestamps and preview links) and **wait for their answer**; apply their changes, set `"confirmed": true` only after they confirm. Done when `research done` and the job has its clips and shorts.
2. **Doctor.** `python3 -m pipeline doctor`. Done when every line is `ok`.
3. **Run.** `python3 -m pipeline run jobs/<name>.json` in the background (downloads, voice separation and master encodes take minutes per clip). It makes the clip cuts, edit sources, look sheets and a `plan.draft.json` per clip. Done when the clip table shows `proxy` and `look` done for every clip.
4. **Plan** every clip the `next:` list marks NEEDS PLAN, with `/hype-edit`. The draft already carries the clip's style (`phonk-hype` for gameplay, `talk` for reactions), its mode (`segment` inside a montage or ranking: no hook, outro or music of its own) and research's payoff hint. Done when every clip has a `plan.json` built from frames you looked at.
5. **Build.** `run` again. Done when every clip shows `build done` and each check is `ok`.
6. **Review** every snap sheet named in `next:` against the taste in `/hype-edit`. Fix `plan.json` and `run` again until each sheet passes. Done when you have looked at every sheet after the last build.
7. **Render.** `python3 -m pipeline render jobs/<name>.json` in the background: each clip's edit (about 3 min per clip), then each short (a single is its clip's render; a montage or ranking is composed: cuts, rank slams, one music bed, outro). Done when the shorts table shows every short `done` and each loudness line is within −16 to −13 LUFS; else apply the printed `mix_gain_db` to that clip's plan, `run`, `render`. For a montage or ranking, snapshot the composed short (`npx hyperframes snapshot --frames 8` in `workspace/<job>/compose/<short>/`) and look at it.

Report to the person: the `final/` folder, one line per short (format, what is in it, length), anything dropped or soft, and the loudness check.

## Rules

- Outputs live only in `workspace/` (git-ignored). Code, jobs, skills and docs are what get committed.
- `--clips 1 3` limits any command to those clip ids (and the shorts that use them); use it to redo one clip.
- `run --no-master` skips the slow master encodes while plans are being written; `render --draft` is a 15 fps proxy render of the clips for a quick watch.
