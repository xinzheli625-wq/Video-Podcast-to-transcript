"""
Task-related Pydantic Schemas
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Celery task states."""
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    REVOKED = "revoked"


class TaskProgress(BaseModel):
    """Task progress information."""

    step: str = Field(..., description="Current step")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    message: str = Field(..., description="Progress message")


class TaskInfo(BaseModel):
    """Task information response."""

    task_id: str = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Task status")
    url: str = Field(..., description="Source URL")
    platform: str = Field(..., description="Platform")
    created_at: datetime = Field(..., description="Task creation time")
    started_at: Optional[datetime] = Field(None, description="Task start time")
    completed_at: Optional[datetime] = Field(None, description="Task completion time")
    updated_at: Optional[datetime] = Field(None, description="Last update time")
    progress: Optional[TaskProgress] = Field(None, description="Current progress")
    result: Optional[Dict[str, Any]] = Field(None, description="Task result if completed")
    error: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123",
                "status": "started",
                "url": "https://www.youtube.com/watch?v=xxx",
                "platform": "youtube",
                "created_at": "2024-01-01T00:00:00Z",
                "started_at": "2024-01-01T00:00:01Z",
                "completed_at": None,
                "progress": {
                    "step": "transcribing",
                    "progress": 50,
                    "message": "正在识别... 50%",
                },
                "result": None,
                "error": None,
            }
        }


class TaskListResponse(BaseModel):
    """Task list response."""

    tasks: list[TaskInfo] = Field(..., description="List of tasks")
    total: int = Field(..., description="Total number of tasks")
    page: int = Field(1, description="Current page")
    page_size: int = Field(20, description="Page size")


class TaskStatistics(BaseModel):
    """Task statistics."""

    total: int = Field(..., description="Total tasks")
    pending: int = Field(..., description="Pending tasks")
    started: int = Field(..., description="Started tasks")
    success: int = Field(..., description="Successful tasks")
    failure: int = Field(..., description="Failed tasks")
    retry: int = Field(..., description="Retrying tasks")


class DownloadUrls(BaseModel):
    """Download URLs for output files."""

    task_id: str = Field(..., description="Task ID")
    files: Dict[str, str] = Field(..., description="File URLs by format")
