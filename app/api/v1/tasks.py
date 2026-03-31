"""
Task Management API Endpoints
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.schemas.task import DownloadUrls, TaskInfo, TaskListResponse, TaskStatistics, TaskStatus
from app.services.task_service import TaskService

router = APIRouter()


def get_task_service() -> TaskService:
    """Dependency to get TaskService instance."""
    return TaskService()


@router.get(
    "/tasks/{task_id}",
    response_model=TaskInfo,
    summary="Get task status and results",
    description="Query the status and results of a transcription task by its ID.",
)
async def get_task(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
) -> TaskInfo:
    """
    Get task information by ID.

    - **task_id**: The task ID returned when creating the transcription

    Returns the task status, progress, and results (if completed).
    """
    task_info = task_service.get_task(task_id)

    if not task_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return task_info


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="List all tasks",
    description="List all transcription tasks with pagination.",
)
async def list_tasks(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    task_service: TaskService = Depends(get_task_service),
) -> TaskListResponse:
    """
    List all transcription tasks.

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **status**: Filter by status (pending, started, success, failure)

    Returns a paginated list of tasks.
    """
    tasks, total = task_service.list_tasks(
        page=page,
        page_size=page_size,
        status=status,
    )

    return TaskListResponse(
        tasks=tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tasks/{task_id}/download",
    summary="Download task output file",
    description="Download a specific output file (md, txt) for a completed task.",
)
async def download_file(
    task_id: str,
    format: str = Query(..., description="File format: srt, vtt, md, or txt"),
    task_service: TaskService = Depends(get_task_service),
):
    """
    Download task output file.

    - **task_id**: The task ID
    - **format**: File format (srt, vtt, md, txt)

    Returns the file content.
    """
    task_info = task_service.get_task(task_id)

    if not task_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    if task_info.status != TaskStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed yet. Current status: {task_info.status.value}",
        )

    # Map format to file extension and MIME type (only txt and md supported)
    format_map = {
        "md": ("transcription.md", "text/markdown", ".md"),
        "txt": ("transcription.txt", "text/plain", ".txt"),
    }

    if format not in format_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid format: {format}. Supported: md, txt",
        )

    filename, media_type, ext = format_map[format]
    file_path = Path("temp") / task_id / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {filename}",
        )

    from starlette.responses import FileResponse as StarletteFileResponse
    
    # Use Starlette's FileResponse with proper headers for download
    response = StarletteFileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=f"transcription_{task_id[:8]}{ext}",
        headers={
            "Content-Disposition": f'attachment; filename="transcription_{task_id[:8]}{ext}"',
        }
    )
    return response


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Delete a task and its associated files.",
)
async def delete_task(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
):
    """
    Delete a task.

    - **task_id**: The task ID to delete

    Returns 204 No Content on success.
    """
    success = task_service.delete_task(task_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return None
