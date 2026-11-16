"""Read-only Google Drive access with a service account (no extra libraries beyond google-auth + requests).

Setup: create a service account, download its JSON key into the GCP_SERVICE_ACCOUNT_JSON secret, and share the
Drive folder with the service account's e-mail address as Viewer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

API = "https://www.googleapis.com/drive/v3"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FIELDS = "nextPageToken, files(id, name, mimeType, size, createdTime, md5Checksum)"


def session() -> AuthorizedSession:
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise SystemExit("GCP_SERVICE_ACCOUNT_JSON is not set (GitHub: Settings > Secrets and variables > Actions)")
    creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    return AuthorizedSession(creds)


def list_videos(s: AuthorizedSession, folder_id: str) -> list[dict]:
    """Every video directly inside the folder (not recursive)."""
    out, token = [], None
    while True:
        r = s.get(f"{API}/files", params={
            "q": f"'{folder_id}' in parents and trashed = false and mimeType contains 'video/'",
            "fields": FIELDS, "pageSize": 200, "pageToken": token,
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
        }, timeout=60)
        r.raise_for_status()
        body = r.json()
        out += body.get("files", [])
        token = body.get("nextPageToken")
        if not token:
            return out


def download(s: AuthorizedSession, file_id: str, dest: Path) -> Path:
    with s.get(f"{API}/files/{file_id}", params={"alt": "media", "supportsAllDrives": "true"},
               stream=True, timeout=600) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest
