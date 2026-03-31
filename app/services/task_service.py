"""
Task Service - Simplified version without Celery/Redis
Uses SQLite for task storage
"""
import json
import os
import shutil
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from app.config import settings
from app.schemas.task import TaskInfo, TaskProgress, TaskStatus


class TaskService:
    """Service for managing transcription tasks using SQLite."""

    def __init__(self):
        """Initialize task service with SQLite database."""
        self.db_path = Path("data/tasks.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with tasks table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    progress INTEGER DEFAULT 0,
                    message TEXT DEFAULT '',
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def create_task(
        self,
        task_id: str,
        url: str,
        platform: str,
        language: str,
        webhook_url: Optional[str] = None,
    ) -> None:
        """Store task metadata in SQLite."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO tasks 
                   (task_id, url, platform, language, status, progress, message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, url, platform, language, "PENDING", 0, "等待处理...", now, now)
            )
            conn.commit()

    def update_task_status(
        self,
        task_id: str,
        status: str,
        progress: int = 0,
        message: str = "",
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update task status in SQLite."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            if result is not None:
                conn.execute(
                    """UPDATE tasks SET status=?, progress=?, message=?, result=?, updated_at=?
                       WHERE task_id=?""",
                    (status, progress, message, json.dumps(result), now, task_id)
                )
            elif error is not None:
                conn.execute(
                    """UPDATE tasks SET status=?, progress=?, message=?, error=?, updated_at=?
                       WHERE task_id=?""",
                    (status, progress, message, error, now, task_id)
                )
            else:
                conn.execute(
                    """UPDATE tasks SET status=?, progress=?, message=?, updated_at=?
                       WHERE task_id=?""",
                    (status, progress, message, now, task_id)
                )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task information by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
            row = cursor.fetchone()
            
            if not row:
                return None

            # Map status
            status_map = {
                "PENDING": TaskStatus.PENDING,
                "STARTED": TaskStatus.STARTED,
                "SUCCESS": TaskStatus.SUCCESS,
                "FAILURE": TaskStatus.FAILURE,
            }
            status = status_map.get(row["status"], TaskStatus.PENDING)

            # Build progress
            progress = None
            if row["status"] in ["STARTED", "PENDING"]:
                progress = TaskProgress(
                    step="processing",
                    progress=row["progress"] or 0,
                    message=row["message"] or "处理中...",
                )

            # Parse result
            result = None
            if row["result"]:
                try:
                    result = json.loads(row["result"])
                except:
                    pass

            # Parse timestamps
            created_at = datetime.fromisoformat(row["created_at"])
            updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
            
            # For completed/failed tasks, use updated_at as completed_at
            completed_at = updated_at if status in [TaskStatus.SUCCESS, TaskStatus.FAILURE] else None
            
            return TaskInfo(
                task_id=row["task_id"],
                status=status,
                url=row["url"],
                platform=row["platform"],
                created_at=created_at,
                completed_at=completed_at,
                updated_at=updated_at,
                progress=progress,
                result=result,
                error=row["error"],
            )

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[List[TaskInfo], int]:
        """List all tasks with pagination."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get total count
            if status:
                cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status=?", (status.upper(),))
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM tasks")
            total = cursor.fetchone()[0]
            
            # Get paginated tasks
            offset = (page - 1) * page_size
            if status:
                cursor = conn.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status.upper(), page_size, offset)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (page_size, offset)
                )
            
            rows = cursor.fetchall()
            tasks = []
            for row in rows:
                task = self.get_task(row["task_id"])
                if task:
                    tasks.append(task)
            
            return tasks, total

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its associated files."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,))
            if not cursor.fetchone():
                return False
            
            conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            conn.commit()
        
        # Cleanup files
        self._cleanup_task_files(task_id)
        return True

    def _cleanup_task_files(self, task_id: str) -> None:
        """Clean up temporary and output files."""
        cleanup_dirs = [
            os.path.join(settings.temp_dir, task_id),
            os.path.join("data", "outputs", task_id),
        ]
        
        for directory in cleanup_dirs:
            if directory and os.path.exists(directory):
                try:
                    shutil.rmtree(directory)
                except:
                    pass

    def get_statistics(self) -> dict:
        """Get task statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status='STARTED' THEN 1 ELSE 0 END) as started,
                    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status='FAILURE' THEN 1 ELSE 0 END) as failure
                FROM tasks
            """)
            row = cursor.fetchone()
            return {
                "total": row[0] or 0,
                "pending": row[1] or 0,
                "started": row[2] or 0,
                "success": row[3] or 0,
                "failure": row[4] or 0,
            }
