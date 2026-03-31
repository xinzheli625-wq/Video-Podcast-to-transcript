"""
Pydantic Schemas for Transcription API
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Platform(str, Enum):
    """Supported platforms."""
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    XIAOYUZHOU = "xiaoyuzhou"


class Language(str, Enum):
    """Supported languages."""
    ZH = "zh"
    EN = "en"
    JA = "ja"
    KO = "ko"
    FR = "fr"
    DE = "de"
    ES = "es"
    RU = "ru"
    AUTO = "auto"


class OutputFormat(str, Enum):
    """Supported output formats."""
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    MD = "md"


class ProcessingMode(str, Enum):
    """LLM post-processing mode."""
    HYBRID = "hybrid"           # Whisper + LLM processing
    WHISPER_ONLY = "whisper_only"  # Only Whisper, no LLM
    LLM_ONLY = "llm_only"       # LLM processing only (if implemented)


class TranscriptionRequest(BaseModel):
    """Request schema for transcription."""

    url: HttpUrl = Field(
        ...,
        description="Video/audio URL (YouTube, Bilibili, Xiaoyuzhou)",
        examples=["https://www.youtube.com/watch?v=xxx"],
    )

    platform: Optional[Platform] = Field(
        default=None,
        description="Platform type (auto-detected if not provided)",
    )

    language: Language = Field(
        default=Language.ZH,
        description="Audio language",
    )

    initial_prompt: Optional[str] = Field(
        default=None,
        description="Initial prompt to guide transcription",
        examples=["这是一段关于航母的军事分析视频"],
    )

    hotwords: Optional[str] = Field(
        default=None,
        description="Hotwords to improve recognition accuracy",
        examples=["肯尼迪号,福特级,尼米兹级,电磁弹射,F-35"],
    )

    output_formats: List[OutputFormat] = Field(
        default=[OutputFormat.TXT, OutputFormat.SRT, OutputFormat.MD],
        description="Output formats to generate",
    )

    processing_mode: ProcessingMode = Field(
        default=ProcessingMode.HYBRID,
        description="Post-processing mode: hybrid (Whisper+LLM) or whisper_only",
    )

    webhook_url: Optional[HttpUrl] = Field(
        default=None,
        description="Webhook URL to notify when transcription is complete",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate URL."""
        url_str = str(v)
        if not any(domain in url_str for domain in [
            "youtube.com", "youtu.be",
            "bilibili.com", "b23.tv",
            "xiaoyuzhoufm.com"
        ]):
            raise ValueError("URL must be from YouTube, Bilibili, or Xiaoyuzhou")
        return v


class TranscriptionSegment(BaseModel):
    """Transcription segment with timestamps."""

    id: int = Field(..., description="Segment ID")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text")


class OutputFile(BaseModel):
    """Output file information."""

    format: str = Field(..., description="File format")
    filename: str = Field(..., description="File name")
    content: str = Field(..., description="File content")


class TranscriptionResponse(BaseModel):
    """Response schema for transcription request."""

    task_id: str = Field(..., description="Task ID for tracking")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Status message")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123",
                "status": "pending",
                "message": "Transcription task queued",
                "created_at": "2024-01-01T00:00:00Z",
            }
        }


class TranscriptionResult(BaseModel):
    """Complete transcription result."""

    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status")
    url: str = Field(..., description="Source URL")
    platform: str = Field(..., description="Platform")
    language: str = Field(..., description="Language")
    duration: float = Field(..., description="Audio duration in seconds")
    text: str = Field(..., description="Full transcribed text")
    segments: List[TranscriptionSegment] = Field(..., description="Transcription segments")
    segments_count: int = Field(..., description="Number of segments")
    output_files: Dict[str, OutputFile] = Field(..., description="Output files by format")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123",
                "status": "completed",
                "url": "https://www.youtube.com/watch?v=xxx",
                "platform": "youtube",
                "language": "zh",
                "duration": 3600.0,
                "text": "Full transcribed text...",
                "segments": [],
                "segments_count": 100,
                "output_files": {},
                "created_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:10:00Z",
            }
        }
