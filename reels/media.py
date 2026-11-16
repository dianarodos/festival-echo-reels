"""Check a video against Facebook Reels rules before uploading it (needs ffprobe)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

MIN_S, MAX_S = 3, 90          # Facebook Reels length
MAX_BYTES = 1_000_000_000     # keep uploads well under 1 GB


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = d["streams"][0]
    return {"width": int(st["width"]), "height": int(st["height"]), "duration": float(d["format"]["duration"])}


def problems(info: dict, size: int) -> list[str]:
    bad = []
    if not MIN_S <= info["duration"] <= MAX_S:
        bad.append(f"length {info['duration']:.0f}s (Reels must be {MIN_S}-{MAX_S}s)")
    if info["height"] <= info["width"]:
        bad.append(f"not vertical ({info['width']}x{info['height']}; Reels need 9:16)")
    if size > MAX_BYTES:
        bad.append(f"file is {size / 1e9:.1f} GB (limit here {MAX_BYTES / 1e9:.0f} GB)")
    return bad
