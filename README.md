# yt-saver

A tool to download YouTube videos and upload them to cloud storage using GitHub Actions for stealthy processing.

## Features

- Download YouTube videos or audio using yt-dlp
- Upload to Aliyun Drive or Gofile
- Use GitHub Actions to avoid local IP detection
- Support for cookies for restricted content
- Automatic cleanup of GitHub Actions runs

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/yt-saver.git
   cd yt-saver
   ```

2. Install dependencies using UV:
   ```bash
   uv pip install -r requirements-local.txt
   ```

3. Install Playwright browser:
   ```bash
   playwright install chromium
   ```

## Configuration

### Aliyun Drive Setup

1. Run the script once to authenticate:
   ```bash
   python3 youtube.py https://youtu.be/example --upload-to ali
   ```
   This will prompt for Aliyun Drive authentication and save the refresh token to `~/.config/yt-saver/aliyundrive.json`.

### Cookies (Optional)

If you need to access restricted YouTube content, create a `cookies.txt` file in the project root with your YouTube cookies.

## Usage

### Basic Usage

Download audio (default):
```bash
python3 youtube.py https://youtu.be/VIDEO_ID
```

Download video:
```bash
python3 youtube.py https://youtu.be/VIDEO_ID --type video
```

### Upload Destinations

Upload to Aliyun Drive (default):
```bash
python3 youtube.py https://youtu.be/VIDEO_ID --upload-to ali
```

Upload to Gofile:
```bash
python3 youtube.py https://youtu.be/VIDEO_ID --upload-to gofile
```

### GitHub Actions Branch

The workflow runs on the `main` branch by default.

### Help

Show help message:
```bash
python3 youtube.py --help
```

## How It Works

1. The script triggers a GitHub Actions workflow to download the video using yt-dlp
2. The workflow uploads the file to the specified cloud storage
3. The script downloads the file from cloud storage to your local machine
4. All GitHub Actions runs are automatically deleted for privacy

## Requirements

- Python 3.8+
- GitHub CLI (`gh`) configured with repository access
- Aliyun Drive account (for ali upload)
- Cookies file (optional, for restricted content)

## GitHub Actions Setup

The workflow requires the following secrets in your GitHub repository:

- `YOUTUBE_COOKIES`: Your YouTube cookies (optional)
- `ALIYUNDRIVE_REFRESH_TOKEN`: Your Aliyun Drive refresh token (auto-set by script)

## Troubleshooting

### Authentication Issues

- Ensure GitHub CLI is logged in: `gh auth login`
- Check repository permissions for workflows and secrets

### Download Failures

- Verify the YouTube URL is valid
- Check if cookies are required for the video
- Ensure yt-dlp is up to date

### Upload Issues

- For Aliyun Drive: Re-run authentication
- For Gofile: Check network connectivity

## License

MIT License
