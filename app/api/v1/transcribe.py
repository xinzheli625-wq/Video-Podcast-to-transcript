"""
Transcription API Endpoints - With LLM Post-processing
"""
import uuid
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

from app.schemas.transcribe import (
    Language,
    OutputFormat,
    Platform,
    TranscriptionRequest,
    TranscriptionResponse,
)
from app.services.task_service import TaskService
from app.config import settings
from core.downloader import AudioDownloader
from core.audio_processor import AudioProcessor
from core.transcriber import WhisperTranscriber
from utils.export_utils import save_all_formats
from utils.llm_processor import TranscriptLLMProcessor, ProcessingMode

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize components
audio_downloader = AudioDownloader()
audio_processor = AudioProcessor()
llm_processor = None  # Lazy initialization

def get_llm_processor():
    """Lazy initialization of LLM processor."""
    global llm_processor
    if llm_processor is None:
        try:
            llm_processor = TranscriptLLMProcessor()
        except Exception as e:
            print(f"[WARNING] Failed to initialize LLM processor: {e}")
            return None
    return llm_processor

# Pre-load Whisper model at startup to avoid long wait during first transcription
print("[INFO] Pre-loading Whisper model...")
try:
    transcriber = WhisperTranscriber()
    # Access model property to trigger loading
    _ = transcriber.model
    print("[INFO] Whisper model loaded successfully!")
except Exception as e:
    print(f"[WARNING] Failed to pre-load Whisper model: {e}")
    print("[WARNING] Model will be loaded on first transcription request")
    transcriber = None

print("[INFO] Transcription components initialized successfully")


def get_task_service() -> TaskService:
    """Dependency to get TaskService instance."""
    return TaskService()


async def _process_with_llm(segments: list, initial_prompt: str = "") -> dict:
    """Process segments with LLM for semantic correction and speaker diarization."""
    if not settings.volcengine_api_key:
        print("[LLM] No API key configured, skipping LLM processing")
        return {
            "diarized_transcript": None,
            "cleaned_text": "\n".join([s.get("text", "") for s in segments]),
        }
    
    processor = get_llm_processor()
    if processor is None:
        print("[LLM] LLM processor not available, using raw transcription")
        return {
            "diarized_transcript": None,
            "cleaned_text": "\n".join([s.get("text", "") for s in segments]),
        }
    
    try:
        result = await processor.process_full(
            segments=segments,
            skills_context=initial_prompt,
            mode=ProcessingMode.HYBRID,
            generate_summary=False,
        )
        return {
            "diarized_transcript": result.diarized_transcript.to_dict() if result.diarized_transcript else None,
            "cleaned_text": result.cleaned_text,
            "tokens_used": result.tokens_used,
            "processing_time_ms": result.processing_time_ms,
        }
    except Exception as e:
        # LLM processing failed, fall back to raw text
        print(f"[LLM] Processing failed: {e}, using raw transcription")
        return {
            "diarized_transcript": None,
            "cleaned_text": "\n".join([s.get("text", "") for s in segments]),
            "error": str(e),
        }


def run_transcription(task_id: str, url: str, platform: str, language: str,
                     initial_prompt: Optional[str], hotwords: Optional[str],
                     output_formats: list, task_service: TaskService,
                     processing_mode: str = "hybrid"):
    """Run transcription synchronously with optional LLM post-processing."""
    import os
    import time
    from pathlib import Path
    
    temp_files = []
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print(f"[TASK {task_id[:8]}] Starting transcription")
    print(f"[TASK {task_id[:8]}] URL: {url}")
    print(f"[TASK {task_id[:8]}] Platform: {platform}, Language: {language}")
    print(f"{'='*60}\n")
    
    try:
        # Update status to started
        task_service.update_task_status(task_id, "STARTED", progress=10, 
                                       message="正在下载音视频...")
        
        # Step 1: Download
        print(f"[TASK {task_id[:8]}] Step 1/5: Downloading audio...")
        input_path = audio_downloader.download(url=url, platform=platform or "auto")
        temp_files.append(input_path)
        print(f"[TASK {task_id[:8]}] Downloaded: {input_path}")
        
        task_service.update_task_status(task_id, "STARTED", progress=25,
                                       message="正在处理音频...")
        
        # Step 2: Audio processing
        print(f"[TASK {task_id[:8]}] Step 2/5: Processing audio...")
        wav_path = audio_processor.convert_to_wav(input_path)
        temp_files.append(wav_path)
        duration = audio_processor.get_duration(wav_path)
        print(f"[TASK {task_id[:8]}] Audio duration: {duration:.1f}s")
        
        task_service.update_task_status(task_id, "STARTED", progress=40,
                                       message="正在进行语音识别...")
        
        # Step 3: Transcription (Whisper)
        print(f"[TASK {task_id[:8]}] Step 3/5: Running Whisper transcription...")
        print(f"[TASK {task_id[:8]}] This may take a while depending on audio length...")
        
        # Ensure transcriber is initialized
        global transcriber
        if transcriber is None:
            print(f"[TASK {task_id[:8]}] Initializing Whisper model (first time)...")
            task_service.update_task_status(task_id, "STARTED", progress=42,
                                           message="正在加载Whisper模型，首次运行需要下载（约500MB-3GB，请耐心等待）...")
            transcriber = WhisperTranscriber()
            task_service.update_task_status(task_id, "STARTED", progress=45,
                                           message="Whisper模型加载完成，开始语音识别...")
        
        # Progress callback that updates both console and database
        last_progress_update = 0
        def progress_callback(progress):
            nonlocal last_progress_update
            pct = int(progress * 100)
            # Map Whisper progress (0-100) to overall progress (40-65)
            overall_progress = 40 + int(progress * 25)
            
            # Update console every 10%
            if pct % 10 == 0:
                print(f"[TASK {task_id[:8]}] Whisper progress: {pct}%")
            
            # Update database every 5% to reduce DB writes
            if pct - last_progress_update >= 5:
                task_service.update_task_status(
                    task_id, "STARTED", 
                    progress=overall_progress,
                    message=f"正在语音识别... {pct}%"
                )
                last_progress_update = pct
        
        transcription_result = transcriber.transcribe(
            audio_path=wav_path,
            language=language,
            initial_prompt=initial_prompt,
            hotwords=hotwords,
            progress_callback=progress_callback,
        )
        
        segments = transcription_result["segments"]
        full_text = transcription_result["text"]
        print(f"[TASK {task_id[:8]}] Whisper complete: {len(segments)} segments, {len(full_text)} chars")
        
        # Step 4: LLM Post-processing (if enabled)
        llm_result = None
        if settings.volcengine_api_key and processing_mode != "whisper_only":
            task_service.update_task_status(task_id, "STARTED", progress=65,
                                           message="正在进行语义纠错和说话人分离...")
            
            print(f"[TASK {task_id[:8]}] Step 4/5: LLM post-processing...")
            print(f"[TASK {task_id[:8]}] Sending {len(segments)} segments to LLM...")
            
            # Run LLM processing in async loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                llm_result = loop.run_until_complete(
                    _process_with_llm(segments, initial_prompt or "")
                )
                if llm_result.get("diarized_transcript"):
                    full_text = llm_result.get("cleaned_text", full_text)
                    print(f"[TASK {task_id[:8]}] LLM processing complete: {llm_result.get('tokens_used', 0)} tokens")
                elif llm_result.get("error"):
                    print(f"[TASK {task_id[:8]}] LLM processing error: {llm_result.get('error')}")
                else:
                    print(f"[TASK {task_id[:8]}] LLM processing skipped (no API key or disabled)")
            finally:
                loop.close()
        else:
            print(f"[TASK {task_id[:8]}] Step 4/5: Skipping LLM (no API key or whisper_only mode)")
        
        task_service.update_task_status(task_id, "STARTED", progress=85,
                                       message="正在导出文件...")
        
        # Step 5: Export (only txt and md formats)
        # Use LLM-processed text if available, otherwise use original
        llm_diarized = llm_result and llm_result.get("diarized_transcript")
        llm_text = llm_result and llm_result.get("cleaned_text")
        
        print(f"[TASK {task_id[:8]}] Step 5/5: Exporting files...")
        print(f"[TASK {task_id[:8]}] Using LLM result: {bool(llm_result)}, Diarized: {bool(llm_diarized)}, Has cleaned_text: {bool(llm_text)}")
        
        # Reconstruct cleaned_text from diarized_transcript if needed
        if llm_diarized and not llm_text:
            turns = llm_diarized.get("turns", [])
            if turns:
                llm_text = "\n\n".join([
                    f"{turn.get('speaker', '未知')}: {turn.get('text', '').strip()}"
                    for turn in turns if turn.get('text', '').strip()
                ])
                print(f"[TASK {task_id[:8]}] Reconstructed cleaned_text from {len(turns)} turns ({len(llm_text)} chars)")
        
        output_dir = Path("temp") / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate TXT file - use LLM cleaned text if available
        txt_path = output_dir / "transcription.txt"
        if llm_text:
            # Use LLM processed text
            txt_content = llm_text
            print(f"[TASK {task_id[:8]}] Saving LLM-processed text to TXT ({len(txt_content)} chars)")
        else:
            # Fallback to original segments
            txt_content = "\n".join([s.get("text", "").strip() for s in segments if s.get("text", "").strip()])
            print(f"[TASK {task_id[:8]}] Saving original text to TXT ({len(txt_content)} chars)")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        
        task_service.update_task_status(task_id, "STARTED", progress=90,
                                       message="正在生成 Markdown...")
        
        # Generate MD file - use diarized format if available
        md_path = output_dir / "transcription.md"
        md_lines = ["# 转录结果", ""]
        
        if llm_diarized and llm_diarized.get("turns"):
            # Use LLM diarized format (speaker-separated)
            print(f"[TASK {task_id[:8]}] Saving diarized dialogue to MD ({len(llm_diarized['turns'])} turns)")
            for turn in llm_diarized["turns"]:
                speaker = turn.get("speaker", "未知")
                turn_start_time = turn.get("start_time", "")
                text = turn.get("text", "").strip()
                emotion = turn.get("emotion", "")
                if text:
                    emotion_tag = f" [{emotion}]" if emotion else ""
                    md_lines.append(f"**【{speaker}】** {turn_start_time}{emotion_tag}: {text}")
                    md_lines.append("")  # Empty line between turns
        else:
            # Fallback to timestamped segments
            print(f"[TASK {task_id[:8]}] Saving timestamped segments to MD")
            for seg in segments:
                start = seg.get("start", 0)
                text = seg.get("text", "").strip()
                if text:
                    hours = int(start // 3600)
                    minutes = int((start % 3600) // 60)
                    secs = int(start % 60)
                    timestamp = f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
                    md_lines.append(f"{timestamp} {text}")
        
        md_lines.extend(["", "---", "", "*Generated by Audio Transcriber*"])
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        
        # Also copy to outputs folder for easy access
        try:
            outputs_dir = Path("outputs")
            outputs_dir.mkdir(exist_ok=True)
            from datetime import datetime
            import shutil
            
            # Create folder name with timestamp and video ID
            now = datetime.now()
            date_str = now.strftime('%Y%m%d_%H%M%S')
            
            # Try to extract video ID from URL
            video_id = 'unknown'
            try:
                import re
                if 'bilibili.com' in url:
                    match = re.search(r'BV\w+', url)
                    if match:
                        video_id = match.group(0)
            except:
                pass
            
            task_output_dir = outputs_dir / f"{date_str}_{video_id}_{task_id[:8]}"
            task_output_dir.mkdir(exist_ok=True)
            
            # Copy files
            shutil.copy2(txt_path, task_output_dir / "transcription.txt")
            shutil.copy2(md_path, task_output_dir / "transcription.md")
            print(f"[TASK {task_id[:8]}] Also saved to outputs folder: {task_output_dir.name}")
        except Exception as e:
            print(f"[TASK {task_id[:8]}] Warning: Could not copy to outputs folder: {e}")
        
        files = {
            "txt": str(txt_path),
            "md": str(md_path),
        }
        print(f"[TASK {task_id[:8]}] Exported: {list(files.keys())}")
        
        # Cleanup downloaded audio files (keep output files)
        for f in temp_files:
            try:
                if Path(f).exists() and "_16k.wav" in str(f):
                    Path(f).unlink()
                    print(f"[TASK {task_id[:8]}] Cleaned up: {f}")
            except:
                pass
        
        # Prepare result with HTTP-accessible file URLs
        # Convert local paths to API download URLs
        file_urls = {}
        for fmt, path in files.items():
            # Create download URL: /api/v1/tasks/{task_id}/download?format={fmt}
            file_urls[fmt] = f"/api/v1/tasks/{task_id}/download?format={fmt}"
        
        result_data = {
            "task_id": task_id,
            "final_text": full_text[:2000] + "..." if len(full_text) > 2000 else full_text,
            "files": file_urls,
            "duration": duration,
            "segment_count": len(segments),
            "whisper_text": transcription_result["text"][:1000] + "..." if len(transcription_result["text"]) > 1000 else transcription_result["text"],
        }
        
        # Add LLM result if available
        if llm_result:
            result_data["llm_processed"] = True
            result_data["diarized_transcript"] = llm_result.get("diarized_transcript")
            result_data["tokens_used"] = llm_result.get("tokens_used")
            if llm_result.get("error"):
                result_data["llm_error"] = llm_result.get("error")
        else:
            result_data["llm_processed"] = False
        
        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"[TASK {task_id[:8]}] COMPLETED in {elapsed:.1f}s")
        print(f"[TASK {task_id[:8]}] {len(segments)} segments, {len(full_text)} chars")
        print(f"{'='*60}\n")
        
        # Update status to success
        task_service.update_task_status(
            task_id, "SUCCESS", progress=100,
            message="转录完成",
            result=result_data
        )
        
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        
        print(f"\n{'='*60}")
        print(f"[TASK {task_id[:8]}] FAILED after {elapsed:.1f}s")
        print(f"[TASK {task_id[:8]}] Error: {error_msg}")
        import traceback
        print(f"[TASK {task_id[:8]}] Traceback:")
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        # Update status to failure
        task_service.update_task_status(
            task_id, "FAILURE", progress=0,
            message=f"转录失败: {error_msg}",
            error=error_msg
        )
        
        # Cleanup
        for f in temp_files:
            try:
                if Path(f).exists():
                    Path(f).unlink()
            except:
                pass


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_transcription(
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
    task_service: TaskService = Depends(get_task_service),
) -> TranscriptionResponse:
    """Create a new transcription task."""
    try:
        # Detect platform
        platform = request.platform
        if not platform:
            platform = _detect_platform(str(request.url))

        # Generate task ID
        task_id = str(uuid.uuid4())

        # Create task record
        task_service.create_task(
            task_id=task_id,
            url=str(request.url),
            platform=platform.value if isinstance(platform, Platform) else platform,
            language=request.language.value if isinstance(request.language, Language) else request.language,
        )

        # Determine processing mode
        processing_mode = getattr(request, 'processing_mode', 'hybrid') or 'hybrid'
        
        # Run transcription in background
        background_tasks.add_task(
            run_transcription,
            task_id=task_id,
            url=str(request.url),
            platform=platform.value if isinstance(platform, Platform) else platform,
            language=request.language.value if isinstance(request.language, Language) else request.language,
            initial_prompt=request.initial_prompt,
            hotwords=request.hotwords,
            output_formats=[fmt.value for fmt in request.output_formats],
            task_service=task_service,
            processing_mode=processing_mode,
        )

        return TranscriptionResponse(
            task_id=task_id,
            status="started",
            message="Transcription task started",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create transcription task: {str(e)}",
        )


def _detect_platform(url: str) -> Platform:
    """Detect platform from URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if "youtube.com" in hostname or "youtu.be" in hostname:
        return Platform.YOUTUBE
    elif "bilibili.com" in hostname or "b23.tv" in hostname:
        return Platform.BILIBILI
    elif "xiaoyuzhoufm.com" in hostname:
        return Platform.XIAOYUZHOU
    else:
        raise ValueError(f"Unsupported platform for URL: {url}")
