"""
Whisper Transcription using faster-whisper
"""
import os
from typing import Callable, Dict, List, Optional

from faster_whisper import WhisperModel

from app.config import settings


class WhisperTranscriber:
    """Whisper transcription wrapper."""

    _instance = None
    _model = None

    def __new__(cls, *args, **kwargs):
        """Singleton pattern to avoid loading model multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        """
        Initialize transcriber.

        Args:
            model_size: Model size (tiny, base, small, medium, large-v1, large-v2, large-v3)
            device: Device (cpu, cuda)
            compute_type: Compute type (int8, int8_float16, int16, float16, float32)
        """
        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self._load_model()

    def _load_model(self):
        """Load Whisper model if not already loaded."""
        if WhisperTranscriber._model is None:
            print(f"Loading Whisper model: {self.model_size} ({self.device}, {self.compute_type})")
            print(f"Loading model from local cache only (offline mode)...")
            import time
            start = time.time()
            WhisperTranscriber._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,  # Use local model only to avoid network delays
            )
            elapsed = time.time() - start
            print(f"Model loaded successfully in {elapsed:.2f}s!")

    @property
    def model(self):
        """Get loaded model."""
        return WhisperTranscriber._model

    def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
        initial_prompt: str = None,
        hotwords: str = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Dict:
        """
        Transcribe audio file.

        Args:
            audio_path: Path to audio file
            language: Language code (zh, en, ja, etc.)
            initial_prompt: Initial prompt for transcription
            hotwords: Hotwords for better recognition
            progress_callback: Progress callback function (0.0 - 1.0)

        Returns:
            Dict with text, segments, and duration
        """
        # Build transcription parameters
        kwargs = {
            "beam_size": 5,
            "best_of": 5,
            "temperature": 0.0,
            "vad_filter": True,
            "vad_parameters": {
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 300,
                "threshold": 0.3,
            },
            "language": language,
            "condition_on_previous_text": True,
            "repetition_penalty": 1.2,
            "no_repeat_ngram_size": 3,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            "no_speech_threshold": 0.6,
        }

        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        if hotwords:
            kwargs["hotwords"] = hotwords

        # Run transcription
        segments, info = self.model.transcribe(audio_path, **kwargs)

        # Process segments
        duration = getattr(info, "duration", 0) or 0
        text_parts = []
        segment_list = []

        last_progress = 0.0

        for segment in segments:
            # Build segment dict
            seg_dict = {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            }
            segment_list.append(seg_dict)
            text_parts.append(segment.text.strip())

            # Update progress
            if progress_callback and duration > 0:
                progress = min(1.0, segment.end / duration)
                if progress - last_progress > 0.05:  # Update every 5%
                    progress_callback(progress)
                    last_progress = progress

        # Final progress
        if progress_callback:
            progress_callback(1.0)

        return {
            "text": " ".join(text_parts),
            "segments": segment_list,
            "duration": duration,
            "language": getattr(info, "language", language),
        }

    @staticmethod
    def cleanup():
        """Unload model and free memory."""
        if WhisperTranscriber._model is not None:
            del WhisperTranscriber._model
            WhisperTranscriber._model = None
            import gc
            gc.collect()
            print("Model unloaded.")
