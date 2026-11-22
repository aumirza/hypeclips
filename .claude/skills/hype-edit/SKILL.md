---
name: hype-edit
description: Hype edit a gameplay clip into a dynamic short (speed ramps, slow-mo payoff, punch-ins, shake, flash, stamp text, SFX, music drop on the payoff) with the hypeedit library and HyperFrames. Use when writing or fixing a clip's edit plan, reviewing a hype edit, or adding a move, beat kind or style to hypeedit.
---

# Hype edit

A **hype edit** turns one clip into a short built around a single **payoff**: everything before it builds toward it, everything after releases. You read the footage, write an **edit plan** in the shared vocabulary, and `hypeedit` turns the plan into a HyperFrames project. You decide *what happens when*; the library owns *how it looks and sounds*.

Inside a job, `/clip-pipeline` runs everything around the plan (sources, sheets, build, snap, render); this skill is the plan and the review. Standalone, the same library runs as `python3 -m hypeedit prep|look|build|snap|render` (see `hypeedit/__main__.py`).

The vocabulary (beats, moves, text slots, plan schema) is [references/vocabulary.md](references/vocabulary.md): read it before writing a plan. How to read beats in a given kind of footage (shooter, driving/stunt, sports, other) is [references/genres.md](references/genres.md).

**Styles and modes.** The draft names both. `phonk-hype` is for gameplay (slow-mo payoff, kill-cam, stamp, boom, music drop); `talk` is for reactions and funny bits (the voice is the point: no slow-mo, a gentle punch-in on the punchline, an optional stamp, a quiet music bed). Mode `full` makes the clip a whole short (hook at frame 0, outro question, music); `segment` makes it one part of a montage or ranking, so it has no hook, outro or music, and its plan needs only beats and an optional stamp.

**Proxy and master.** Sheets, builds, snaps and the Studio preview use the 540×960 proxy; only the final render uses the 1080×1920 master. Plans are in source seconds and output pixels, so they hold for both.

## Writing a plan

Work in the clip's folder, `workspace/<job>/edits/clip_NN_slug/`.

1. **Look.** Read `look/overview.jpg` and `look/audio_envelope.txt`, then make 10 fps strips around every candidate moment (`python3 -m pipeline look jobs/<job>.json --clip N --detail A,B`) until each beat is pinned. Done when you can name the payoff frame to 0.05 s and its focus point in output pixels (grid cells are 108×192), and every hit, whip, build and lull is placed.
2. **Write.** Fill `plan.draft.json` (its `_context` has the clip's label, title, stream range and, from research, `kind`, `hook` and `payoff_hint_t`: where to start looking, in source seconds) and save it as `plan.json`. Text in the platform's voice: hook ≤ 3 words a line, stamp ≤ 2 words, outro a question that invites comments. Done when every beat in it is something you saw on a frame, not a guess.
3. **Review** the snap sheet after the build against the taste below. Fix the *plan* (beat times, focus, text) and rebuild; change the library only when the fault would recur on other clips. Done when the payoff frame shows the impact inside the slow-mo, the stamp clears the focus, and frame 0 reads as a thumbnail.

A rebuild overwrites the generated `project/`. If the person edited it in the HyperFrames app or Studio, run `npx hyperframes history --since mine` in the project first and carry their changes into the plan or the library.

## Taste

The phonk-hype style, learned on the clip 03 headshot (`talk` keeps the same type and safe-zone rules, without the slow-mo and kill-cam). Numbers live in `hypeedit/style.py`; these are the rules behind them.

- **One payoff.** Every clip has exactly one; it gets the slow-mo, the punch, the flash, the stamp, the boom and the music drop. Secondary impacts are hits and get a fraction of that.
- **Frame 0 is the thumbnail.** The hook is fully on screen at frame 0 and leaves on the first whip.
- **Compress the wait, stretch the moment.** Repetitive tension plays fast (build), the payoff plays at 0.22×, the dead stretch after plays slightly fast (lull).
- **The music drop lands on the payoff frame**, with a short dip just before it; the riser crests there too.
- **Every sound has a cause on screen**, peaking one frame after its picture. Whooshes go on whips and zoom-outs, never wallpaper.
- **Effects stay on the footage.** Grade, exposure and bloom go through HyperFrames media treatment; overlays are type, bars, brackets and light, never CSS filters on video.
- **Words sit in the safe band** (y 168–1330, clear of the right-hand action rail) and land then hold dead still.
- **Zoom stays modest** (≤ 1.3×): sources are upscaled crops and blur fast.
- **Ending is a question** held at least 2 s.

## Extending

New moves, beat kinds and styles go in the library, so every later clip gets them: a move is one function in `hypeedit/moves.py` called from `compose()`, a style is a dict in `hypeedit/style.py`, a beat kind is added to `plan.py` and to `references/vocabulary.md` together. Search the HyperFrames registry (`/hyperframes-registry`) before hand-building a visual. After any library change, rebuild the reference clip (`hypeedit/examples/clip03.plan.json`, live copy at `workspace/carry_gta6/edits/clip_03_clean_headshot/`) and compare its snap sheet against the previous one.
