"""
Audio Downloader using yt-dlp
"""
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

from yt_dlp import YoutubeDL

from app.config import settings


class AudioDownloader:
    """Download audio from video platforms."""

    def __init__(self):
        self.temp_dir = Path(settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        platform: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        Download audio from URL.

        Args:
            url: Video URL
            platform: Platform name (youtube, bilibili, xiaoyuzhou)
            progress_callback: Progress callback function (0.0 - 1.0)

        Returns:
            Path to downloaded audio file
        """
        # Create temp directory for this download
        temp_path = self.temp_dir / f"dl_{os.urandom(4).hex()}"
        temp_path.mkdir(exist_ok=True)

        output_template = str(temp_path / "%(id)s.%(ext)s")

        # Progress hook
        def progress_hook(d):
            if d.get("status") == "downloading" and progress_callback:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                if total > 0:
                    progress_callback(downloaded / total)

        # yt-dlp options
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "cachedir": False,
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)

                if os.path.exists(file_path):
                    return file_path
                else:
                    raise FileNotFoundError(f"Downloaded file not found: {file_path}")

        except Exception as e:
            # Cleanup on error
            if temp_path.exists():
                import shutil
                shutil.rmtree(temp_path, ignore_errors=True)
            raise e
