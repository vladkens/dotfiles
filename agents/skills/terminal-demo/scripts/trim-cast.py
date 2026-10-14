# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Speed up chosen stretches of an asciicast recording, such as network downloads.

Each --speed CMD MARKER SECONDS scales the delays from the end of the typed command CMD up to and
including the first later event whose output contains MARKER, so that stretch plays in SECONDS.
Everything else keeps its real timing. Color codes are ignored when matching CMD.

    uv run --script trim-cast.py raw.cast demo.cast \
        --speed "wavo pull parakeet-v3" "/tmp/hf/models--" 2.5
"""

import argparse
import json
import re

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("src")
parser.add_argument("dst")
parser.add_argument(
    "--speed", nargs=3, action="append", default=[], metavar=("CMD", "MARKER", "SECONDS")
)
args = parser.parse_args()

lines = open(args.src, encoding="utf-8").read().splitlines()
header, events = lines[0], [json.loads(line) for line in lines[1:]]

segments = [(cmd + "\r\n", marker, float(secs)) for cmd, marker, secs in args.speed]
text, starts = "", {}
for i, (_, code, data) in enumerate(events):
    if code != "o":
        continue
    text = ANSI.sub("", text + data)[-400:]
    for k, (cmd, _, _) in enumerate(segments):
        if k not in starts and text.endswith(cmd):
            starts[k] = i + 1

for k, (cmd, marker, target) in enumerate(segments):
    if k not in starts:
        raise SystemExit(f"command not found in the recording: {cmd.strip()!r}")
    a = starts[k]
    b = next((j for j in range(a, len(events)) if marker in events[j][2]), None)
    if b is None:
        raise SystemExit(f"marker {marker!r} not found after {cmd.strip()!r}")
    real = sum(e[0] for e in events[a : b + 1])
    for e in events[a : b + 1]:
        e[0] = round(e[0] * target / real, 6)
    print(f"{cmd.strip()!r}: {real:.1f}s -> {target}s ({b - a + 1} events)")

with open(args.dst, "w", encoding="utf-8") as f:
    f.write(header + "\n")
    for e in events:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(f"total {sum(e[0] for e in events):.1f}s")
