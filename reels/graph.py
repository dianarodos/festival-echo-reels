"""Facebook Graph API helpers. The Page token never appears in anything printed or raised."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v25.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"


class PostError(Exception):
    pass


def token() -> str:
    t = os.environ.get("META_PAGE_TOKEN", "").strip()
    if not t:
        raise PostError("META_PAGE_TOKEN is not set (GitHub: Settings > Secrets and variables > Actions)")
    return t


def call(method: str, path: str, **params) -> dict:
    tok = token()
    r = requests.request(
        method, f"{GRAPH}/{path}",
        data={**params, "access_token": tok} if method == "POST" else None,
        params={**params, "access_token": tok} if method == "GET" else None,
        timeout=60,
    )
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    if r.status_code >= 400 or "error" in body:
        err = body.get("error", body)
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        hint = ""
        if isinstance(err, dict) and err.get("code") in (190, 102):
            hint = " -> the Page token expired or was revoked: make a new one and update META_PAGE_TOKEN"
        raise PostError(f"{method} {path.split('?')[0]}: {msg.replace(tok, '***')}{hint}")
    return body


def post_reel(page_id: str, path: Path, caption: str) -> str:
    """Upload an MP4 as a Facebook Reel: start -> upload bytes -> finish/publish -> wait until ready."""
    start = call("POST", f"{page_id}/video_reels", upload_phase="start")
    vid = start["video_id"]
    size = path.stat().st_size
    with path.open("rb") as fh:
        r = requests.post(
            f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{vid}",
            headers={"Authorization": f"OAuth {token()}", "offset": "0", "file_size": str(size)},
            data=fh, timeout=1200,
        )
    try:
        ok = r.status_code < 400 and r.json().get("success")
    except ValueError:
        ok = False
    if not ok:
        raise PostError(f"Facebook upload failed: {r.text[:300].replace(token(), '***')}")
    call("POST", f"{page_id}/video_reels", upload_phase="finish", video_id=vid,
         video_state="PUBLISHED", description=caption)
    for _ in range(90):                                   # processing usually takes 10-90 s
        st = call("GET", vid, fields="status").get("status", {})
        if st.get("video_status") == "ready" or st.get("publishing_phase", {}).get("status") == "complete":
            return vid
        if st.get("video_status") == "error" or st.get("processing_phase", {}).get("status") == "error":
            raise PostError(f"Facebook could not process the video: {json.dumps(st)[:300]}")
        time.sleep(5)
    return vid                                            # still processing; Facebook finishes on its own


def comment(object_id: str, text: str) -> str:
    return call("POST", f"{object_id}/comments", message=text).get("id", "")
