"""Post the next unposted video from a Google Drive folder to a Facebook Page as a Reel.

    python -m reels.run                 # post the next video in the queue
    python -m reels.run --dry-run       # download + check the next video, post nothing
    python -m reels.run --file-id ID    # post one specific Drive file (even if already posted: add --force)

Env: META_PAGE_TOKEN, FB_PAGE_ID, DRIVE_FOLDER_ID, GCP_SERVICE_ACCOUNT_JSON; optional QUEUE_ORDER=name|created.
Every attempt is logged in data/posted.json, which the workflow commits back so the queue survives between runs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from reels import drive, graph, media

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "posted.json"
CAPTIONS = ROOT / "config" / "captions.json"
PRIORITY = ROOT / "config" / "queue.json"


def note(line: str) -> None:
    """Append a line to the summary file the workflow turns into a ping (if SUMMARY_FILE is set)."""
    path = os.environ.get("SUMMARY_FILE")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def load_log() -> list[dict]:
    return json.loads(LOG.read_text()) if LOG.exists() else []


def save_log(log: list[dict]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False))


def load_captions() -> dict:
    return json.loads(CAPTIONS.read_text()) if CAPTIONS.exists() else {"default": "", "by_file": {}, "link_comment": ""}


def caption_for(name: str, cfg: dict) -> str:
    stem = Path(name).stem
    by_file = cfg.get("by_file", {})
    return by_file.get(name) or by_file.get(stem) or cfg.get("default", "")


def load_priority() -> list[str]:
    """Name fragments (case-insensitive) that jump the queue, in the order they should post."""
    try:
        return json.loads(PRIORITY.read_text(encoding="utf-8")).get("priority", [])
    except (OSError, ValueError):
        return []


def queue(videos: list[dict], log: list[dict], order: str, priority: list[str] | None = None) -> list[dict]:
    """Videos not yet handled (posted or skipped), in posting order. `priority` fragments go first, in that order."""
    done = {e["drive_id"] for e in log if e.get("status") in ("posted", "skipped")}
    todo = [v for v in videos if v["id"] not in done]
    key = (lambda v: v["createdTime"]) if order == "created" else (lambda v: v["name"].lower())
    pri = [p.lower() for p in (priority or [])]

    def rank(v):
        n = v["name"].lower()
        return next((i for i, p in enumerate(pri) if p in n), len(pri))

    return sorted(todo, key=lambda v: (rank(v), key(v)))


def recycle_queue(videos: list[dict], log: list[dict], todo: list[dict]) -> list[dict]:
    """Already-posted videos, least recently posted first: the fallback when nothing new in the queue is usable."""
    last = {}
    for e in log:
        if e.get("status") == "posted":
            last[e["drive_id"]] = max(last.get(e["drive_id"], ""), e.get("at", ""))
    fresh = {v["id"] for v in todo}
    return sorted((v for v in videos if v["id"] in last and v["id"] not in fresh), key=lambda v: last[v["id"]])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file-id", default="")
    ap.add_argument("--force", action="store_true", help="post even if this file was already posted")
    ap.add_argument("--count", type=int, default=1, help="how many videos to post this run")
    a = ap.parse_args(argv)

    s = drive.session()
    videos = drive.list_videos(s, os.environ["DRIVE_FOLDER_ID"])
    log, cfg = load_log(), load_captions()
    if a.file_id:
        todo = [v for v in videos if v["id"] == a.file_id]
        if not todo:
            print(f"file {a.file_id} is not in the Drive folder"); return 1
    else:
        todo = queue(videos, log, os.environ.get("QUEUE_ORDER", "name"), load_priority())
    recycle = [] if a.file_id else recycle_queue(videos, log, todo)
    print(f"{len(videos)} videos in Drive, {len(todo)} waiting in the queue, {len(recycle)} to repost if none of those is usable")
    if not todo and not recycle:
        print("Nothing to post: add more videos to the Drive folder.")
        note("Nothing to post: the Drive folder has no more usable videos. Add more!"); return 0

    posted, failed = 0, False
    with tempfile.TemporaryDirectory() as tmp:
        recycled = {v["id"] for v in recycle}
        for v in todo + recycle:
            if posted >= a.count:
                break
            if v["id"] in recycled and not posted:
                if v is recycle[0]:
                    print("No new usable video in the queue: reposting the least recently posted one.")
                    note("No new usable video in the queue, so an already-posted Reel was reposted. Add more videos to Drive!")
            entry = {"drive_id": v["id"], "name": v["name"], "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
            already = any(e["drive_id"] == v["id"] and e.get("status") == "posted" for e in log)
            if already and not a.force and v["id"] not in recycled:
                print(f"  {v['name']}: already posted; skipped"); continue
            path = drive.download(s, v["id"], Path(tmp) / "video.mp4")
            bad = media.problems(media.probe(path), path.stat().st_size)
            if bad:
                print(f"  {v['name']}: SKIPPED, {'; '.join(bad)}")
                if not a.dry_run:
                    log.append({**entry, "status": "skipped", "reason": "; ".join(bad)})
                continue
            caption = caption_for(v["name"], cfg)
            if a.dry_run:
                print(f"  {v['name']}: OK to post. Caption would be: {caption[:80]!r}"); posted += 1; continue
            try:
                vid = graph.post_reel(os.environ["FB_PAGE_ID"], path, caption)
                entry.update(status="posted", fb_id=vid)
                if cfg.get("link_comment"):
                    try:
                        entry["comment_id"] = graph.comment(vid, cfg["link_comment"])
                    except graph.PostError as e:
                        print(f"  {v['name']}: Reel posted, but the link comment failed: {e}")
                print(f"  {v['name']}: posted Reel (id {vid})")
                note(f"Posted: {v['name']} - https://www.facebook.com/reel/{vid}")
                posted += 1
            except graph.PostError as e:
                failed = True
                entry.update(status="failed", error=str(e))     # not 'skipped': the next run tries it again
                print(f"  {v['name']}: FAILED: {e}")
                note(f"FAILED: {v['name']} - {e}")
                log.append(entry); break
            log.append(entry)
    if not a.dry_run:
        save_log(log[-500:])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
