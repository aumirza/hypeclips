# Findings

Measured on one real stream (CarryisLive, GTA 6, 9.8 h, Hindi/Hinglish, YouTube `irNhWMG560k`) in November 2026. Each finding drove a decision in the code.

## Picking from text alone is often wrong

- The 9 clips of the first job had been picked by an AI reading text only. Checking frames: 4 of 9 did not show what their titles claimed (a "long-range snipe" was walking with a basketball; "NPC ambush" and "recoil fight" were just driving), 1 more only partly.
- In the research run, 2 of 8 shortlisted moments looked great in text but showed a settings menu and a cartoon BRB screen.
- **Decision:** 360p verify sheets for every shortlisted moment, and a selection gate that must look at them. Picks must say in `why` what makes the moment visible.

## Audio cannot find gameplay action

- Tested three detectors (high-band transients, stereo-side energy to cancel the centred voice, crest factor) against frame-verified clips: no feature separated gunfights from driving; engine and road noise scored as high as gunfire.
- **Decision:** no game-action audio signal. Action is found from the transcript and crowd signals, then confirmed on verify sheets. For gameplay-heavy requests, `research.scan: "full"` reads the whole stream.

## Captions

- YouTube's auto-*translated* tracks (e.g. Hindi to English) return HTTP 429 reliably; the original-language track (`hi-orig`) downloads in about a second (5.3 MB for 9.8 h).
- Devanagari costs roughly 3-4x the tokens of the same speech in Latin letters. Romanizing (`दिस इट्स होल इमोशन` → `dis its hol imoshan`) keeps it readable for Claude, which reads Hinglish fine.
- **Decision:** caption order `["en", "orig"]` with 429 backoff; romanize non-Latin; the picker writes titles and hooks in `output_language` regardless.

## Crowd signals

- Comment timestamps were the strongest signal (312 mentions in 1,370 comments, about 75 s to fetch), but noisy: copy-pasted spam, index lists of many timestamps, and the most-liked timestamps pointed at risqué scenes ("thank me later 🌚", 3,100 likes).
- Live-chat replay and most-replayed data were absent on this stream.
- **Decision:** likes-weighted comments, spam counted once, multi-timestamp comments split their weight; the picking guide tells the AI to read the comment, not just the count. Every signal is optional and skipped when missing.

## Efficiency

- Reading only the top signal windows (16 × 4 min) was about a quarter of the full transcript's text.
- Full-stream audio: the HLS (m3u8) low-bitrate track crawled; plain HTTPS with 8 connections downloaded 214 MB in about a minute. `-drc` tracks are excluded (dynamic-range compression flattens loudness).
- ffmpeg `astats` with per-frame metadata took over 10 min on 9.8 h of audio; one decode plus numpy takes under 2 min.

## Quality

- 1080p sources give a 522 px wide vertical crop (about 2x upscale, soft). The stream had 1440p: a 696 px crop and visibly crisper. Downloads now default to 1440p; clipper output is CRF 17.
- Zoom above about 1.3x on upscaled crops looks blurry; phonk-hype caps the punch-in there.
- Measured mixes landed at about −14.6 to −14.8 LUFS, no clipping, after scaling levels once.

## Bugs found by running it

- A renumbered clip reused another moment's raw download and voice stems (raws were keyed by clip id and height only). Fixed: range in the stamp, derived audio cleared on re-fetch.
- Titles with apostrophes broke the clipper's `drawtext` (a straight quote can't be escaped inside ffmpeg's quoted values). Fixed with the typographic apostrophe.
- A duplicate element id doubled a CSS offset in the ranking header. The HyperFrames check and snapshots caught it, which is why every build is snapped and looked at.
