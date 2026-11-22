# Open items

## Unverified at the end of the build session

- **First full ranking render.** Job `jobs/carry_gta6_research.json` (ranking "Top 3 wildest GTA 6 moments" + one single) was rendering when the session ended. The ranking composer was checked and snapshotted with stand-in clips; the real render is not yet watched. Check: `python3 -m pipeline status jobs/carry_gta6_research.json`, then look at `workspace/carry_gta6_research/final/`.
- **Montage format** has not been rendered on real clips yet.
- Only one stream has been through research: a non-GTA stream, an English stream and a Twitch VOD are all untested.

## Known gaps

- **Facecam layout.** Talk clips whose energy is in the voice look weak in a centre crop (menus, cut-aways, black loading frames; the facecam is cropped out). A `react-cam` style (facecam stacked over gameplay + word captions, as in the original gta6-clipper's render) is the next improvement.
- **Captions on talk clips.** No burned-in subtitles yet; for non-English streams they would need translation.
- **Suggestive content.** The kiss-cutscene clip in the test ranking shows a second of underwear in the crop; the picking guide filters sexual moments but romance cutscenes are borderline. Decide per channel.
- **Twitch/Kick research** has no captions path (no Whisper installed) and no Twitch VOD chat or community-clips signal yet.
- **Live streams.** The original tool's rolling-buffer live mode (`live.py`) was not ported.
- **Old raws.** `jobs/carry_gta6.json` still has 1080p raws for some clips; the next `run` re-fetches them at 1440p.

## Housekeeping

- The old GitHub repo `aumirza/clips` still exists; deleting it needs `gh auth refresh -h github.com -s delete_repo` first.
- `gta6-clipper.zip` and `gta6-live-clipper.zip` sit in the repo root (git-ignored) and can be deleted.
- `workspace/carry_gta6_research/edits/clip_03_caught_in_first_minutes/` is left over from before the clips were renumbered.
