# yt-saver

A framework for downloading YouTube videos/audio via GitHub Actions and automatically transferring them to third-party cloud storage. Users can extend support for additional storage providers by implementing plugins in the `providers/` directory.

---

## Features

- **Remote download**: Leverages GitHub Actions runners to bypass local IP restrictions.
- **Pluggable storage**: Switch between Aliyun Drive, OneDrive, Gofile, or any custom provider.
- **Batch tasks**: Define multiple download tasks in `tasks.yml` and run them in one shot.
- **Cookie automation**: Built-in Playwright helper to log in to YouTube and export `cookies.txt`.
- **Privacy first**: Automatically deletes GitHub Actions run logs after each task.

---

## Quick Start

### 1. Prerequisites

- Python 3.8+
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- (Optional) [rclone](https://rclone.org/) — required only for OneDrive local retrieval

### 2. Install Dependencies

```bash
uv venv .venv
source .venv/bin/activate
uv pip install pyyaml requests playwright
```

### 3. Single Task (CLI)

```bash
# Download audio to OneDrive (default)
python3 youtube.py <YOUTUBE_URL>

# Download video to Aliyun Drive
python3 youtube.py <YOUTUBE_URL> --mode video --storage aliyun --token <REFRESH_TOKEN>

# Custom filename (no extension)
python3 youtube.py <YOUTUBE_URL> --filename my_song
```

### 4. Batch Tasks (YAML)

Edit `tasks.yml`:

```yaml
config:
  mode: "audio"          # audio | video
  storage: "onedrive"    # onedrive | aliyun | gofile
  branch: "main"
  verbose: true
  # token: "your_token"  # required when storage is aliyun

tasks:
  "https://www.youtube.com/watch?v=EXAMPLE1": "song_one"
  "https://www.youtube.com/watch?v=EXAMPLE2":
    filename: "song_two"
    mode: "video"
```

Run:

```bash
python3 main.py
```

---

## Architecture

```
.
├── youtube.py              # Single-task entry: CLI args → trigger Actions → monitor → retrieve
├── main.py                 # Batch entry: reads tasks.yml, loops over youtube.py logic
├── utils.py                # Playwright helper: auto-login YouTube → export Netscape cookies.txt
├── tasks.yml               # Batch task configuration
├── cookies.txt             # YouTube cookies (optional, gitignored)
├── .github/workflows/
│   └── download.yml        # GitHub Actions workflow definition
└── providers/              # Storage provider plugins
    ├── base.py             # Abstract base class: StorageProvider
    ├── aliyun.py           # Aliyun Drive provider (local retrieve + cloud delete)
    ├── aliclient.py        # Aliyun Open API client (token refresh, chunked upload/download)
    ├── aliyun.sh           # Shell script invoked inside GitHub Actions for Aliyun upload
    ├── onedrive.py         # OneDrive provider (local retrieve via rclone + cloud delete)
    ├── odclient.py         # OneDrive Graph API client (chunked upload, stream download)
    ├── onedrive.sh         # Shell script invoked inside GitHub Actions for OneDrive upload
    ├── gofile.py           # Gofile provider (print download link only)
    └── gofile.sh           # Shell script invoked inside GitHub Actions for Gofile upload
```

### How It Works

1. **Local trigger** — `youtube.py` calls `gh workflow run` to start the remote workflow.
2. **Remote download** — GitHub Actions installs `yt-dlp`, downloads the media, and uploads it to the selected cloud via `providers/<name>.sh`.
3. **Result exchange** — The shell script prints a standardized block:
   ```
   ---RESULT_START---
   KEY: VALUE
   ---RESULT_END---
   ```
4. **Local retrieve** — The matching `providers/<name>.py` parses the log block, downloads the file to `~/Downloads` (configurable), and deletes the cloud copy.
5. **Cleanup** — The GitHub Actions run record is deleted for privacy.

---

## Adding a New Storage Provider

To add a provider (e.g., `mystorage`):

1. **Implement the local handler** — Create `providers/mystorage.py`:

   ```python
   import re
   from .base import StorageProvider

   class MystorageProvider(StorageProvider):
       def handle_result(self, logs, token=None):
           match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
           if not match:
               return
           data = match.group(1)
           # Parse keys, download to self.download_dir, then clean up cloud copy
   ```

2. **Implement the remote uploader** — Create `providers/mystorage.sh`:

   ```bash
   #!/bin/bash
   FILE_PATH="$1"
   # Upload $FILE_PATH to your cloud service
   echo "---RESULT_START---"
   echo "MY_KEY: my_value"
   echo "---RESULT_END---"
   ```

3. **Register in `youtube.py`** — Import `MystorageProvider` and add a branch in `monitor_workflow`:

   ```python
   elif storage_type == "mystorage":
       MystorageProvider(config).handle_result(log_stdout, token)
   ```

4. **Register CLI choices** — In `setup_args()`, add `"mystorage"` to the `--storage` choices.

5. **Register in the workflow** — In `.github/workflows/download.yml`, add `"mystorage"` to the `storage_provider` input options.

---

## Security Notes

- `cookies.txt` contains sensitive YouTube credentials and is `.gitignore`d. Never commit it.
- The workflow deletes cookies and downloaded files in its `always()` cleanup step, but tokens may still appear in logs. The local script deletes the run record afterward.
- `youtube.py` uses `shell=True` for `gh` commands. Avoid passing untrusted input directly.

---

## License

MIT License
