"""Captions -> timed lines, and romanization of non-Latin scripts.

YouTube json3 captions arrive as short rolling events; we merge them into
lines of a few seconds so a chunk reads like a transcript. Romanizing
Devanagari (Hindi, Marathi, Nepali) cuts the tokens an AI spends reading by
3-4x; Claude reads romanized Hinglish fine. Other scripts pass through.
"""

from __future__ import annotations

import json
import re
import unicodedata

# ---------------------------------------------------------------- captions


def json3_lines(path, max_gap=1.2, max_len=7.0) -> list[dict]:
    """[{start, end, text}] merged from json3 events."""
    d = json.loads(open(path, encoding="utf-8").read())
    ev = []
    for e in d.get("events", []):
        segs = e.get("segs")
        if not segs:
            continue
        text = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
        if not text:
            continue
        st = e["tStartMs"] / 1000
        ev.append([st, st + e.get("dDurationMs", 2000) / 1000, text])
    lines: list[dict] = []
    for st, en, text in ev:
        if lines and st - lines[-1]["end"] <= max_gap and en - lines[-1]["start"] <= max_len:
            lines[-1]["text"] += " " + text
            lines[-1]["end"] = max(lines[-1]["end"], en)
        else:
            lines.append({"start": round(st, 2), "end": round(en, 2), "text": text})
    for ln in lines:
        ln["end"] = round(ln["end"], 2)
    return lines


# ---------------------------------------------------------------- romanize (Devanagari)

_V = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
      "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e"}
_M = {"ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
      "ौ": "au", "ॉ": "o", "ॅ": "e"}
_C = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
      "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
      "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
      "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
      "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "rh", "फ़": "f", "य़": "y"}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "d", "ढ": "dh", "फ": "f"}
_SIGN = {"ं": "n", "ँ": "n", "ः": "h", "़": "", "्": "", "।": ".", "॥": "."}
_DIGIT = {chr(0x0966 + i): str(i) for i in range(10)}


def _word(w: str) -> str:
    out, i, n = [], 0, len(w)
    while i < n:
        ch = w[i]
        if ch in _C:
            cons = _C[ch]
            if i + 1 < n and w[i + 1] == "़":
                cons = _NUKTA.get(ch, cons)
                i += 1
            nxt = w[i + 1] if i + 1 < n else ""
            if nxt in _M:
                out.append(cons + _M[nxt])
                i += 2
                continue
            if nxt == "्":
                out.append(cons)
                i += 2
                continue
            # inherent vowel, dropped at the end of a word (schwa deletion, roughly)
            out.append(cons + ("a" if i + 1 < n and nxt not in _SIGN else ""))
            i += 1
            continue
        out.append(_V.get(ch) or _M.get(ch) or _SIGN.get(ch, _DIGIT.get(ch, ch)))
        i += 1
    return "".join(out)


_DEVA = re.compile(r"[ऀ-ॿ]+")


def romanize(text: str) -> str:
    # NFD splits precomposed nukta letters (ड़ U+095C) into base + nukta, which _word handles
    return _DEVA.sub(lambda m: _word(m.group(0)), unicodedata.normalize("NFD", text))


def needs_romanize(lines: list[dict]) -> bool:
    sample = "".join(ln["text"] for ln in lines[:400])
    return bool(sample) and sum(1 for c in sample if "ऀ" <= c <= "ॿ") / len(sample) > 0.2
