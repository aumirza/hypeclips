# Hype-edit vocabulary

One language for every clip, whatever the game. **Beats** describe the footage (what happens, in source seconds). **Moves** describe the edit (what we do about it). A plan lists beats and text; the style maps beats to moves.

## Beats

| Beat | Shape | Meaning, any content | Required fields |
| --- | --- | --- | --- |
| `payoff` | point | The one moment the clip exists for. Exactly one per plan. | `t`, `focus` [x, y] output px; `lock: true` when there is a distinct target to bracket |
| `hit` | point | A secondary impact: a shot fired, a bump, a near-miss, taking damage. | `t`; `hurt: true` when the player/vehicle takes it |
| `whip` | point | The in-game camera or subject moves fast (turn, cut, swerve). | `t` |
| `build` | span | Tension that looks the same for a while: aiming, run-up, accelerating toward a ramp. | `t`, `end` |
| `lull` | span | A dead stretch after the payoff: reloading, cruising, walking. | `t`, `end` |

`t`/`end` are seconds in the prepared `source.mp4`. `focus` is where the eye should go at the payoff, in pixels of the 1080×1920 output frame (the detail sheets draw a 108×192 grid). Unlisted time plays at 1×.

## Moves

| Move | Triggered by | Does |
| --- | --- | --- |
| `ramp` | build, lull, payoff | rate lane on the footage: build fast, payoff slow-mo, lull slightly fast; game audio ducks under the slow-mo |
| `hook` | frame 0 | two-line title on screen at frame 0, slam-settles, whips off on the first whip |
| `tease` | first build + `text.tease` | bar text over the build |
| `letterbox` | payoff | black bars slide in for the slow-mo |
| `punch` | payoff; hit clusters | zoom on the focus (payoff), quick small zoom per cluster of hits |
| `lock` | payoff with `lock` | corner brackets close on the focus, turn accent on the shot |
| `flash` | payoff | white flash plus exposure and bloom blow-out on the footage |
| `jolt` | payoff, every hit | deterministic decaying camera shake |
| `stamp` | payoff | `text.stamp` slams with an RGB split, holds through the slow-mo |
| `damage` | hit with `hurt` | red edge vignette plus exposure dip |
| `outro` | end | `text.outro` question, last 2.2 s |
| `bed` | `music` | track enters so its drop lands on the payoff, dips just before |
| sounds | riser and boom (payoff), glitch (stamp, hurt), whoosh (whip, zoom-out, title moves) |

## Text slots

`hook` (1–2 lines, the last is the accent line, ≤ 3 words each), `stamp` (≤ 2 words), `tease` (optional), `outro` (1–2 lines, a question), `accent` (hex colour). They become HyperFrames variables, so the person can change copy in Studio without a rebuild.

## Plan file

```json
{
  "name": "clip_03_clean_headshot",
  "source": "source.mp4",
  "music": { "file": "../../../../assets/music/phonk.mp3" },
  "out_dir": "project",
  "style": "phonk-hype",
  "text": {
    "hook": ["INSANELY CLEAN", "HEADSHOT"],
    "tease": "WAIT FOR IT",
    "stamp": "HEADSHOT",
    "outro": ["CLEAN", "OR LUCKY?"],
    "accent": "#ff3030"
  },
  "beats": [
    { "kind": "whip", "t": 1.6 },
    { "kind": "build", "t": 2.3, "end": 4.7 },
    { "kind": "payoff", "t": 5.65, "focus": [540, 1035], "lock": true, "note": "enemy behind the water tank drops" },
    { "kind": "hit", "t": 8.7 },
    { "kind": "hit", "t": 8.8, "hurt": true }
  ]
}
```

Paths are relative to the plan file. Optional: `out_dir` (the pipeline uses `"project"`), `music.drop` (seconds in the track) to override drop detection, `mix_gain_db` (render prints it when loudness is off), `note` on any beat.
