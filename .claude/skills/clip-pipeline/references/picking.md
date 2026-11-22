# Picking moments

You are the editor of a clips page with millions of followers. Each window file (`research/chunks/wNN.md`) is a few minutes of a stream: its transcript (romanized when the stream isn't in Latin script) with signal markers. Find the moments people actually share, score them harshly, and write them down. The job's `research.brief` says what this stream is and what clips are wanted; the window header lists the job's **kinds** and their lengths.

## Reading the markers

Signals point; they don't decide. A loud line with nothing in it is not a clip; a great moment with no marker can be.

- `CMT n`: viewers timestamped this in the comments (likes-weighted). The strongest crowd signal, but read the comment: people also timestamp risqué or off-topic moments ("thank me later 🌚").
- `REPLAYED n`: YouTube most-replayed.
- `CHAT xN`: chat moving N times faster than usual. Chat reacts a few seconds late: the moment is just before.
- `LOUD +NdB`: the speaker is that much louder than usual (yelling, freaking out).
- `FAST TALK`: talking far more than usual.
- `(no speech)` lines: a strong signal with nobody talking.

No marker detects gameplay action (game audio can't tell a gunfight from driving). Find action from what is said ("maar", "bhaag", "he's shooting", sudden silence after a fight) and from comments; the verify sheet then shows whether it's really on screen. Text alone is often wrong about what's on screen, so `why` should say what makes you think it is visible.

## Kinds

Use the job's kinds. Gameplay kinds (`action`, `fail`) are about what happens **on screen**: their clip is cut tight around the payoff and the streamer's voice is removed, so the moment must work without the talking. Talk kinds (`reaction`, `funny`, `hot_take`) are about what the streamer **says or does**: their clip keeps the voice and starts on the first real sentence.

## Throw out (don't write them)

- Needs context to land (refers to earlier events, inside jokes, "like I said").
- Reading chat, donations, sponsor reads, "subscribe", intermissions, menus, loading, waiting, dead air.
- Caption junk: repeated lines, `[music]`/`[sngeet]`, text that doesn't match the stream.
- Hateful, sexual, or about real people's private lives.

## Scoring (0-10, harsh)

- 9-10: anyone scrolling stops and shares. Instant payoff, no context, strong emotion or a jaw-drop visual.
- 7-8: solid; clear hook in the first 2-3 s, lands on its own.
- 5-6: fine but nobody shares it. Write it only if the window has nothing better.
- below 5: don't write it.

Most windows have 0-2 real moments; many have none. `[]` is a normal answer.

## Boundaries

- Start ON the hook, not on the build-up a minute earlier; end right after the payoff.
- Stay inside the kind's length; the shortlist trims anything longer around `payoff`.
- `payoff`: the second the moment peaks (the kill, the landing, the punchline). Required for gameplay kinds; it is where the hype edit's slow-mo lands.

## Output: `research/picks/wNN.json`

```json
[
  {
    "start": "03:51:38",
    "end": "03:51:58",
    "payoff": "03:51:47",
    "kind": "action",
    "score": 8,
    "hook": "HE CARRIED THE WHOLE SQUAD",
    "title": "He carried the entire squad in one fight",
    "caption": "Swizy never stood a chance 😭 Who's the real carry here?",
    "hashtags": ["#gaming"],
    "why": "comment 'asli game to carry khel raha hai' (91 likes); 'maar maar' then 'gaya!' over 10 s, sounds like a 3-kill fight"
  }
]
```

- Write in `research.output_language` (English unless the job says otherwise), whatever language the stream is in.
- `hook`: on-screen line, up to ~8 words, names the subject and what happens, makes you need to watch.
- `title`: post title, sentence case, under 70 characters. `caption`: one or two short lines ending in a question that gets comments.
- `hashtags`: specific to the moment; the job's `research.hashtags` are added automatically.
- `why`: the evidence (markers, comment text, what is said or seen), so the selection step can judge it.

## The request

The window header shows the job's `research.request`, the person's own words.

- **A request** ("gunfight shorts", "top 5 car stunts", "funniest moments"): pick only moments that serve it, and say in `why` how each one does. A ranking request needs at least as many strong moments as places; if the stream doesn't have them, say so at selection rather than padding.
- **No request**: pick broadly. The selection then **recommends** shorts: what this stream is best for.

## Selection (gate 2): propose shorts

After every window has a picks file, `research` builds `research/shortlist.json`, `report.md` (with preview links) and a 360p contact sheet per moment (`research/verify/<id>.jpg`). Look at every sheet: drop moments whose picture doesn't deliver what the pick promised, and correct `start`/`end`/`payoff` to what you see. Then write `research/selection.json` as **shorts**:

```json
{
  "confirmed": false,
  "shorts": [
    { "format": "ranking", "header": "TOP 3 WILDEST GTA 6 MOMENTS",
      "title": "Top 3 wildest moments from his first GTA 6 stream", "caption": "#1 had him begging 😭 Which was yours?",
      "hashtags": ["#GTA6"], "outro": ["WHICH ONE", "WAS YOUR #1?"],
      "clips": [ { "id": "s05", "payoff": "00:25:17.5" }, "s07", "s01" ] },
    { "format": "montage", "hook": ["3 TIMES GTA 6", "WENT CRAZY"], "outro": ["WHICH ONE", "WAS WILDER?"],
      "clips": [ "s02", "s09" ] },
    { "format": "single", "clips": [ "s03" ] }
  ]
}
```

- **single**: one clip, the whole short (its own hook and outro come from its edit plan).
- **montage**: 2-3 clips on one theme, cut together; give it a `hook` (frame-0 title) and an `outro` question.
- **ranking**: 2-10 clips in **play order, last = #1**; give it a `header` (stays on screen) and an `outro`. Rankings work best at 3-5 places of 6-12 s each (segments are trimmed around their `payoff` to `research.segment_length`), so one ranking stays near a minute.
- A clip belongs to one short. Any field you set on a clip entry overrides the shortlist's (`start`, `end`, `payoff`, `title`, `caption`, `hook`, `hashtags`, `slug`).
- With no request, recommend what the moments support: the strongest moments as singles, and a ranking or montage when several share a theme. Fewer, better shorts beat padding.

## Confirmation (gate 3): the person decides

`research` then writes `research/proposal.md` (every short, its clips in order, timestamps, length, preview links and verify-sheet paths) and stops at NEEDS CONFIRMATION. Show the person the proposal in a few lines per short and wait for their answer. Apply what they change to `selection.json`; when they confirm, set `"confirmed": true` and run `research` again. Never set it without their confirmation.
