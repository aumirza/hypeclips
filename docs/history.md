# History

How the project reached its current shape, in one build session (22 Nov 2026).

1. **Pilot edit.** One downloaded clip (a GTA 6 headshot) hand-edited in HyperFrames: speed ramp, slow-mo payoff, punch-in, shake, flash, "HEADSHOT" stamp, SFX, phonk drop on the kill. The person liked the taste; it became the `phonk-hype` style.
2. **Library and vocabulary.** The edit was generalized into `hypeedit`: a content-agnostic vocabulary (beats: payoff, hit, whip, build, lull; moves: ramp, punch, jolt, flash, stamp…) and a plan file per clip. Rebuilding the pilot from a plan reproduced it within 0.04 s.
3. **Quality.** Proxy for preview, master for render; downloads raised to 1440p after the person asked for sharper output.
4. **Single entry point.** `shorts_clipper.py` became `pipeline/clipper.py` under `python3 -m pipeline`; outputs moved to a git-ignored `workspace/`; repo published (private). Legacy scripts removed; the ranking web UI (`ranking_studio`) moved out to its own folder; the project renamed to **hypeclips**.
5. **Research.** The person's earlier tool (MIT, `vossashtonai/gta6-clipper-windows`: transcript chunks with LOUD/CHAT markers, AI picks) was reviewed. Kept its picking rubric and chunking; fixed what didn't fit (English-only, speech-only signals, no visual check, scores not comparable across chunks, GTA/Windows hardcoding). Built `pipeline research` and tested it on the 9.8 h stream (see findings.md).
6. **Generic audio.** `audio.mode: gunshots` became `audio.source`: original, no_voice, voice_only, muted, per job or per clip.
7. **Shorts.** The person's target: URL, optional request, confirmed timestamps, finished shorts of 1-3 clips or a ranking. Added the `Short` model, request/recommendation, proposal + confirmation gate, the `talk` style, segment mode, and `hypeedit/shortcompose.py` (montage/ranking) so rankings get the same effects as everything else.

Commits: `3ba3d7e` initial, `2fce8bc` research, `e1c2df4` shorts.
