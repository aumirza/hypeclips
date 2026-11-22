"""Fast audio scan (needs numpy; run with the project venv's python).

One ffmpeg decode at 8 kHz mono; writes {"rms_db": [loudness per second]} as JSON.

    .venv/bin/python -m pipeline.research.audioscan <audio> <out.json>
"""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np

SR = 8000


def scan(path: str) -> dict:
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE)
    rms = []
    block = SR * 2 * 60  # one minute of mono s16
    carry = b""
    while True:
        chunk = p.stdout.read(block)
        if not chunk:
            break
        buf = carry + chunk
        usable = len(buf) - len(buf) % (SR * 2)  # whole seconds
        carry = buf[usable:]
        if not usable:
            continue
        x = np.frombuffer(buf[:usable], dtype=np.int16).astype(np.float32).reshape(-1, SR) / 32768.0
        rms += (20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)).round(2).tolist()
    p.wait()
    return {"rms_db": rms}


if __name__ == "__main__":
    out = scan(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(out, f)
