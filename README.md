# festival-echo-reels

Posts one video a day from a Google Drive folder to a Facebook Page as a **Reel**, using the Meta Graph API.
Runs entirely on GitHub Actions (free). Modeled on the Reel poster in `dianarodos/floridabids`.

## How it works
1. A daily workflow (`.github/workflows/post.yml`) lists the videos in your Drive folder.
2. It picks the next one not yet in `data/posted.json` (alphabetical by file name, or by upload date).
3. It downloads it, checks Reels rules (3-90 s, vertical 9:16, under 1 GB) with `ffprobe`.
   A video that breaks the rules is logged as *skipped* and the next one is tried.
4. It uploads it to Facebook as a Reel with the caption from `config/captions.json`, optionally adds a first comment (ticket link).
5. It commits `data/posted.json` so tomorrow it picks the next video. When the folder runs out, it does nothing.

If Facebook rejects an upload (e.g. expired token) the video is logged as *failed*, the run goes red, and the same video is retried next time.

## One-time setup
**1. Google Drive access (service account)**
- Google Cloud Console > create a project > enable the *Google Drive API* > IAM > Service Accounts > create one > Keys > add a JSON key.
- Open the Drive folder with the Reels > Share > add the service account's e-mail (`...@...iam.gserviceaccount.com`) as **Viewer**.
- The folder ID is the last part of the folder URL (`drive.google.com/drive/folders/<THIS>`).

**2. GitHub repo settings** (Settings > Secrets and variables > Actions)
| Type | Name | Value |
|---|---|---|
| Secret | `META_PAGE_TOKEN` | Page access token with Page posting permissions |
| Secret | `GCP_SERVICE_ACCOUNT_JSON` | the whole JSON key file contents |
| Variable | `FB_PAGE_ID` | the Facebook Page's numeric ID |
| Variable | `DRIVE_FOLDER_ID` | the Drive folder ID |
| Variable (optional) | `QUEUE_ORDER` | `name` (default) or `created` |

Also: Settings > Actions > General > Workflow permissions > *Read and write*.

**3. Test it**: Actions tab > *Post next Reel* > Run workflow > tick **dry run**. It downloads and checks the next video and posts nothing. Then run it again without dry run for the first real post.

## Captions
Edit `config/captions.json`: `default` is used for every video; `by_file` overrides it per file name
(`"my-video.mp4": "caption..."`); `link_comment` is posted as the first comment (links in post text are limited by Facebook, comments are not).

## Notes
- Schedule: `cron` in `post.yml` (UTC). Default 14:00 UTC.
- Large files: GitHub runners handle a few GB, but Facebook wants Reels to be small; export for 1080x1920 H.264, ideally under a few hundred MB.
- Page tokens expire if made from a short-lived user token; use a long-lived/never-expiring Page token.
- Run locally: `pip install -r requirements.txt`, set the env vars, `python -m reels.run --dry-run`.
