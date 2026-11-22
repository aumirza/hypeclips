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

## Selection (gate 2)

After every window has a picks file, `research` builds `research/shortlist.json` and `report.md` (with preview links) and a 360p contact sheet per moment in `research/verify/<id>.jpg`. Look at every sheet: drop moments whose picture doesn't deliver what the pick promised, correct `start`/`end`/`payoff` to what you see, and write `research/selection.json` in the order the clips should be numbered:

```json
{ "clips": [ { "id": "s03", "slug": "carried_the_squad", "label": "Carried the Squad", "payoff": "03:51:46.5" } ] }
```

Any field you set overrides the shortlist's (`start`, `end`, `payoff`, `title`, `caption`, `hook`, `hashtags`). Keep `research.count` clips unless fewer deserve it; say so if fewer do.
