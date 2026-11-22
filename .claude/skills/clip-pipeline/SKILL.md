---
name: clip-pipeline
description: Run the clips pipeline end to end, from a job config of stream timestamps to rendered hype-edited shorts in workspace/<job>/final. Use when given a video URL, timestamps or a job config to turn into shorts, or asked to resume, check or render a job.
---

# Clip pipeline

One command drives the whole workflow: `python3 -m pipeline <cmd> jobs/<job>.json`, run from the repo root. Every stage checks its own outputs, so `run` is safe to repeat and only does what is missing or stale. Job format: [jobs/README.md](../../../jobs/README.md). Layout of `workspace/<job>/`: the docstring of `pipeline/job.py`.

The pipeline does the mechanical work; you do the editorial work at two gates: **plan** (read each clip, write its `plan.json`) and **review** (read each snap sheet before the master render).

## Steps

1. **Job.** Put the person's timestamps into `jobs/<name>.json` (copy the shape in `jobs/README.md`; ids unique, slugs snake_case, a title and caption per clip). Done when `python3 -m pipeline status jobs/<name>.json` lists every clip without a config error.
2. **Doctor.** `python3 -m pipeline doctor`. Done when every line is `ok`.
3. **Run.** `python3 -m pipeline run jobs/<name>.json` (run it in the background: downloads, demucs and the master encodes take minutes per clip). It makes the plain shorts, the edit sources, the look sheets and a `plan.draft.json` per clip, then prints the status table and a `next:` list. Done when the table shows `proxy` and `look` done for every clip.
4. **Plan** every clip the `next:` list marks NEEDS PLAN, with `/hype-edit`: read the clip's `look/` sheets (`python3 -m pipeline look jobs/<name>.json --clip N --detail A,B` for 10 fps strips), fill the draft and save it as `plan.json` beside it. Done when every edited clip has a `plan.json` built from frames you looked at. A clip with no real payoff gets `"edit": false` in the job instead of a forced plan; say which and why.
5. **Build.** `run` again. Done when every clip shows `build done` and each check is `ok`.
6. **Review** every snap sheet named in `next:` against the taste in `/hype-edit`. Fix `plan.json` and `run` again until each sheet passes. Done when you have looked at every sheet after the last build.
7. **Render.** `python3 -m pipeline render jobs/<name>.json` (background; about 3 min a clip). Done when every clip shows `render done`, and each loudness line is within −16 to −13 LUFS; else apply the printed `mix_gain_db` to that plan, `run`, `render`.

Report to the person: the `final/` folder, one line per clip (payoff, anything skipped or soft), and the loudness check.

## Rules

- Outputs live only in `workspace/` (git-ignored). Code, jobs, skills and docs are what get committed.
- `--clips 1 3` limits any command to those ids; use it to redo one clip.
- A plain short only (no hype edit): `"edit": {"enabled": false}` in the job.
- `run --no-master` skips the slow master encodes while plans are being written; `render --draft` is a 15 fps proxy render for a quick watch.
