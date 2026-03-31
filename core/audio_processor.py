"""
Audio Processing using ffmpeg
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

try:
    from imageio_ffmpeg import get_ffmpeg_exe
    FFMPEG = get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"


class AudioProcessor:
    """Process audio files for transcription."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def convert_to_wav(
        self,
        input_path: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Convert audio to 16kHz mono WAV format for Whisper.

        Args:
            input_path: Input audio file path
            output_path: Output file path (optional)

        Returns:
            Path to converted WAV file
        """
        if output_path is None:
            output_path = input_path.replace(
                ".m4a", "_16k.wav"
            ).replace(
                ".mp3", "_16k.wav"
            ).replace(
                ".aac", "_16k.wav"
            ).replace(
                ".ogg", "_16k.wav"
            ).replace(
                ".webm", "_16k.wav"
            )

        if not output_path.endswith(".wav"):
            output_path += "_16k.wav"

        cmd = [
            FFMPEG,
            "-nostdin",
            "-y",
            "-i", input_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-f", "wav",
            output_path,
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            if os.path.exists(output_path):
                return output_path
            else:
                raise FileNotFoundError(f"Output file not created: {output_path}")

        except subprocess.CalledProcessError as e:
            print(f"Audio conversion failed: {e}")
            return input_path

    def get_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds."""
        cmd = [
            FFMPEG,
            "-i", audio_path,
            "-f", "null",
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            stderr = result.stderr
            duration_match = __import__('re').search(
                r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})",
                stderr
            )
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = float(duration_match.group(3))
                return hours * 3600 + minutes * 60 + seconds
        except Exception:
            pass

        return 0.0

    def split_audio(
        self,
        audio_path: str,
        segment_duration: int = 600,  # 10 minutes
    ) -> list:
        """Split audio into segments."""
        duration = self.get_duration(audio_path)

        if duration <= segment_duration:
            return [audio_path]

        segments = []
        base_path = audio_path.replace(".wav", "")

        for i, start in enumerate(range(0, int(duration), segment_duration)):
            segment_path = f"{base_path}_seg{i}.wav"

            cmd = [
                FFMPEG,
                "-nostdin",
                "-y",
                "-i", audio_path,
                "-ss", str(start),
                "-t", str(segment_duration),
                "-c", "copy",
                segment_path,
            ]

            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                segments.append(segment_path)
            except subprocess.CalledProcessError:
                continue

        return segments if segments else [audio_path]
