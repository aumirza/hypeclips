# hypeclips

Stream timestamps in, one hype-edited vertical short per clip out; combining clips (rankings, compilations) belongs to a separate project. The single entry point is `python3 -m pipeline` (run from this folder); `/clip-pipeline` is the workflow, `/hype-edit` is the per-clip plan and the style.

- `jobs/` one JSON per source video (format: `jobs/README.md`)
- `pipeline/` the entry point: stages, job paths, and `clipper.py` (download, crop, demucs game audio, plain short)
- `hypeedit/` the edit library: plan → HyperFrames project (vocabulary in `.claude/skills/hype-edit/references/`)
- `assets/music/` local tracks, git-ignored
- `workspace/<job>/` every generated file, git-ignored

Generated media and downloads go only under `workspace/`. Python tools (yt-dlp, demucs) live in `.venv`; the pipeline puts `.venv/bin` on PATH itself, so plain `python3` runs it. After changing `pipeline/clipper.py`, run `python3 -m pipeline.clipper --self-test`.
