"""
LLM Processor - 语义级说话人分离 (Semantic Diarization)

基于火山引擎 DeepSeek V3 实现：
1. 深度语义纠错 + 对话分离
2. Stateful Chunking 保持说话人一致性
3. 剧本式对话重构
"""

import json
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

import tiktoken
from openai import AsyncOpenAI, APIError, RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class ProcessingMode(str, Enum):
    """处理模式"""
    RULE_ONLY = "rule_only"
    LLM_ONLY = "llm_only"
    HYBRID = "hybrid"


@dataclass
class DialogTurn:
    """
    对话轮次 - 剧本式对话的基本单元

    Attributes:
        speaker: 说话人角色（如"主持人"、"嘉宾A"、真实姓名等）
        start_time: 开始时间戳（格式：HH:MM:SS）
        end_time: 结束时间戳（格式：HH:MM:SS，可选）
        text: 清理后的顺滑文本
        emotion: 语气/情绪标记（可选，如"笑着说"、"严肃地"）
    """
    speaker: str
    start_time: str
    text: str
    end_time: Optional[str] = None
    emotion: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "speaker": self.speaker,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "text": self.text,
            "emotion": self.emotion,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DialogTurn":
        return cls(**data)


@dataclass
class DiarizedTranscript:
    """
    带有说话人分离的转录结果

    Attributes:
        turns: 对话轮次列表
        speakers: 检测到的所有说话人列表（去重）
        metadata: 额外的元数据（如处理时间、token消耗等）
    """
    turns: List[DialogTurn] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "turns": [t.to_dict() for t in self.turns],
            "speakers": self.speakers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DiarizedTranscript":
        turns = [DialogTurn.from_dict(t) for t in data.get("turns", [])]
        return cls(
            turns=turns,
            speakers=data.get("speakers", []),
            metadata=data.get("metadata", {}),
        )

    def get_unique_speakers(self) -> List[str]:
        """获取所有唯一的说话人"""
        return list(set(turn.speaker for turn in self.turns))

    def merge_consecutive_same_speaker(self) -> "DiarizedTranscript":
        """合并连续的同一说话人轮次"""
        if not self.turns:
            return self

        merged = []
        current = self.turns[0]

        for turn in self.turns[1:]:
            if turn.speaker == current.speaker:
                # 合并文本，保留最早的时间戳
                current.text += " " + turn.text
                if turn.end_time:
                    current.end_time = turn.end_time
            else:
                merged.append(current)
                current = turn

        merged.append(current)

        return DiarizedTranscript(
            turns=merged,
            speakers=self.speakers,
            metadata=self.metadata,
        )


@dataclass
class Chapter:
    """章节信息（保留用于全局摘要）"""
    timestamp: str
    title: str
    summary: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DocumentInsights:
    """文档洞察（全局摘要，与 DiarizedTranscript 互补）"""
    tldr: str
    key_points: List[str]
    chapters: List[Chapter]

    def to_dict(self) -> Dict:
        return {
            "tldr": self.tldr,
            "key_points": self.key_points,
            "chapters": [c.to_dict() for c in self.chapters],
        }


@dataclass
class ProcessingResult:
    """完整处理结果"""
    diarized_transcript: DiarizedTranscript
    insights: Optional[DocumentInsights]
    processing_time_ms: float
    tokens_used: int
    mode: ProcessingMode
    cleaned_text: str = ""  # 添加这个字段以兼容 transcribe.py


class TranscriptLLMProcessor:
    """
    转录文本 LLM 处理器 - 支持语义级说话人分离
    """

    def __init__(self, mock_mode: bool = False):
        api_key = settings.volcengine_api_key
        if not api_key:
            raise ValueError(
                "Volcengine API key not configured. "
                "Please set VOLCENGINE_API_KEY_ENC in .env file. "
                "Use 'python -m utils.encryption <your_key>' to encrypt."
            )
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.volcengine_base_url,
        )
        self.model = settings.volcengine_model_name
        self.max_tokens = 4096
        self.chunk_size = 3500  # 每个 chunk 的目标 token 数
        self.chunk_overlap = 400  # chunk 之间的重叠
        self.mock_mode = mock_mode

        # 初始化 tokenizer
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        except:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        """计算文本的 token 数"""
        return len(self.tokenizer.encode(text))

    def _format_time(self, seconds: float) -> str:
        """将秒数格式化为 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _build_diarization_prompt(self, previous_context: str = "") -> str:
        """
        构建说话人分离的 System Prompt
        """
        base_prompt = """你是一位资深的播客制作人和速记编辑。请阅读这段带有时间戳的单声道转录文本，将其重构成顺滑的"剧本式"对话文稿。

【核心任务】
1. **识别说话人**：根据内容逻辑、语气词、专业领域等线索，推断每句话的说话人身份（如："主持人"、"嘉宾A"、"嘉宾B"，或文本中提到的真实姓名）。
2. **语义纠错**：修正语音识别错误（同音字、方言），删除无意义的口癖（"呃"、"那个"、"就是"），但保留核心语气和情感。
3. **合并与拆分**：如果连续几个时间段是同一个人在说话，请合并为一个对话轮次；如果一个人说话中有明显的逻辑断点，可以拆分为多个轮次。
4. **时间戳保留**：为每个对话轮次标注最早的开始时间戳。

【输出格式 - 必须严格遵守】
你必须输出一个严格的 JSON 对象，格式如下：
{
    "dialogue": [
        {
            "speaker": "主持人",
            "start_time": "00:05:23",
            "text": "欢迎收听本期节目。今天我们有幸邀请到了一位特别的嘉宾。",
            "emotion": "热情地"
        },
        {
            "speaker": "嘉宾A",
            "start_time": "00:05:45",
            "text": "谢谢主持人的邀请，很高兴能来这里和大家分享。",
            "emotion": "微笑地"
        }
    ],
    "speakers_summary": ["主持人", "嘉宾A"]
}

【规则要求】
1. 所有字段必须存在，不能为空。
2. speaker 命名要有意义（主持人/嘉宾A/嘉宾B/真实姓名）。
3. start_time 格式必须是 HH:MM:SS。
4. text 必须是清理后的顺滑文本，去除口癖。
5. emotion 可选，用于描述语气（如"严肃地"、"笑着说"）。

【特别说明】
- 不要返回任何解释性文字，只返回 JSON。
- 确保 JSON 格式完全合法，可以被 Python 的 json.loads 解析。"""

        if previous_context:
            context_section = f"""

【上下文继承 - 非常重要】
上一段文本中识别到的说话人和对话风格如下，请严格遵守：
{previous_context}

你必须确保：
1. 同一说话人的命名必须完全一致（如上一段叫"嘉宾A"，这一段不能叫"嘉宾甲"）。
2. 说话人的风格、语气要保持连贯。
3. 如果新出现的说话人可能是之前提到的某人，请使用相同的命名。"""
            base_prompt += context_section

        return base_prompt

    def _prepare_segments_for_chunking(self, segments: List[dict]) -> List[str]:
        """
        将 segments 转换为带时间戳的文本行
        """
        lines = []
        for seg in segments:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if text:
                time_str = self._format_time(start)
                lines.append(f"[{time_str}] {text}")
        return lines

    def _chunk_segments(self, segments: List[dict]) -> List[Tuple[List[dict], str]]:
        """
        将 segments 分块，每块约 3500 tokens

        Returns:
            List of (chunk_segments, chunk_text) tuples
        """
        lines = self._prepare_segments_for_chunking(segments)

        chunks = []
        current_chunk_lines = []
        current_chunk_segments = []
        current_tokens = 0

        for i, (line, seg) in enumerate(zip(lines, segments)):
            line_tokens = self._count_tokens(line)

            # 如果当前块已经很大，或者加上这一行会超过限制，则先保存当前块
            if current_tokens + line_tokens > self.chunk_size and current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines)
                chunks.append((current_chunk_segments, chunk_text))

                # 开始新块，保留一些重叠以维持上下文
                overlap_count = min(3, len(current_chunk_lines))
                current_chunk_lines = current_chunk_lines[-overlap_count:]
                current_chunk_segments = current_chunk_segments[-overlap_count:]
                current_tokens = sum(self._count_tokens(l) for l in current_chunk_lines)

            current_chunk_lines.append(line)
            current_chunk_segments.append(seg)
            current_tokens += line_tokens

        # 添加最后一个块
        if current_chunk_lines:
            chunk_text = "\n".join(current_chunk_lines)
            chunks.append((current_chunk_segments, chunk_text))

        return chunks

    def _extract_context_from_dialogue(self, dialogue: List[DialogTurn], max_turns: int = 5) -> str:
        """
        从对话中提取上下文信息，用于传递到下一块
        """
        if not dialogue:
            return ""

        # 获取最后几轮对话
        recent_turns = dialogue[-max_turns:] if len(dialogue) > max_turns else dialogue

        # 提取说话人列表和特点
        speakers = {}
        for turn in recent_turns:
            if turn.speaker not in speakers:
                speakers[turn.speaker] = {
                    "count": 0,
                    "sample_text": turn.text[:50] + "..." if len(turn.text) > 50 else turn.text,
                    "emotion": turn.emotion,
                }
            speakers[turn.speaker]["count"] += 1

        # 构建上下文字符串
        context_lines = ["【已确认的说话人】"]
        for speaker, info in speakers.items():
            context_lines.append(f"- {speaker}: 出现了{info['count']}次")
            if info.get("emotion"):
                context_lines.append(f"  风格: {info['emotion']}")
            context_lines.append(f"  示例: \"{info['sample_text']}\"")

        context_lines.append("\n【最近对话片段】")
        for turn in recent_turns:
            emotion_tag = f"[{turn.emotion}]" if turn.emotion else ""
            context_lines.append(f"{turn.speaker} {emotion_tag}: {turn.text[:80]}...")

        return "\n".join(context_lines)

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_llm_with_json_mode(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
    ) -> Dict:
        """调用 LLM，强制 JSON 输出"""
        if self.mock_mode:
            # Mock 模式返回测试数据
            return self._generate_mock_dialogue_response()

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)

    def _generate_mock_dialogue_response(self) -> Dict:
        """生成 Mock 对话响应（用于测试）"""
        return {
            "dialogue": [
                {
                    "speaker": "主持人",
                    "start_time": "00:00:05",
                    "text": "欢迎大家收听本期节目，今天我们有幸请到了一位特别嘉宾。",
                    "emotion": "热情地"
                },
                {
                    "speaker": "嘉宾A",
                    "start_time": "00:00:15",
                    "text": "谢谢主持人的邀请，很高兴来到这里和大家分享。",
                    "emotion": "微笑地"
                }
            ],
            "speakers_summary": ["主持人", "嘉宾A"]
        }

    async def clean_and_diarize(
        self,
        segments: List[dict],
        skills_context: str = "",
        mode: ProcessingMode = ProcessingMode.HYBRID,
    ) -> DiarizedTranscript:
        """
        清洗并分离说话人 - 核心方法

        Args:
            segments: Whisper 输出的 segments 列表（包含 start, end, text）
            skills_context: Skills Manager 提供的上下文
            mode: 处理模式

        Returns:
            DiarizedTranscript: 带有说话人分离的对话结果
        """
        if mode == ProcessingMode.RULE_ONLY:
            # 仅使用 Skills 预处理，不进行说话人分离
            return self._apply_rules_only(segments)

        # 分块处理
        chunks = self._chunk_segments(segments)
        all_dialogue_turns: List[DialogTurn] = []
        previous_context = ""

        for chunk_idx, (chunk_segments, chunk_text) in enumerate(chunks):
            logger.info(f"Processing chunk {chunk_idx + 1}/{len(chunks)} ({len(chunk_segments)} segments)")

            # 构建 Prompt
            system_prompt = self._build_diarization_prompt(previous_context)

            # 添加 Skills 上下文（如果有）
            user_content = chunk_text
            if skills_context and chunk_idx == 0:
                user_content = f"【术语规范提示】\n{skills_context}\n\n【转录文本】\n{chunk_text}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            try:
                # 调用 LLM
                result = await self._call_llm_with_json_mode(
                    messages,
                    temperature=0.3,
                )

                # 解析对话结果
                dialogue_data = result.get("dialogue", [])
                chunk_turns = []

                for turn_data in dialogue_data:
                    turn = DialogTurn(
                        speaker=turn_data.get("speaker", "未知"),
                        start_time=turn_data.get("start_time", "00:00:00"),
                        end_time=turn_data.get("end_time"),
                        text=turn_data.get("text", "").strip(),
                        emotion=turn_data.get("emotion"),
                    )
                    chunk_turns.append(turn)
                    all_dialogue_turns.append(turn)

                # 提取上下文用于下一块
                previous_context = self._extract_context_from_dialogue(chunk_turns)

            except Exception as e:
                logger.error(f"Chunk {chunk_idx} processing failed: {e}")
                # 失败时保留原始文本作为 fallback，按行拆分
                for seg in chunk_segments:
                    turn = DialogTurn(
                        speaker="未知",
                        start_time=self._format_time(seg.get("start", 0)),
                        end_time=self._format_time(seg.get("end", 0)),
                        text=seg.get("text", "").strip(),
                    )
                    all_dialogue_turns.append(turn)

        # 构建最终结果
        transcript = DiarizedTranscript(
            turns=all_dialogue_turns,
            speakers=list(set(turn.speaker for turn in all_dialogue_turns)),
            metadata={
                "total_turns": len(all_dialogue_turns),
                "processing_chunks": len(chunks),
            }
        )

        # 合并连续同说话人的轮次（可选优化）
        transcript = transcript.merge_consecutive_same_speaker()

        return transcript

    def _apply_rules_only(self, segments: List[dict]) -> DiarizedTranscript:
        """仅应用规则，不分离说话人"""
        turns = []
        for seg in segments:
            turn = DialogTurn(
                speaker="未知",
                start_time=self._format_time(seg.get("start", 0)),
                end_time=self._format_time(seg.get("end", 0)),
                text=seg.get("text", "").strip(),
            )
            turns.append(turn)

        return DiarizedTranscript(
            turns=turns,
            speakers=["未知"],
            metadata={"mode": "rule_only"},
        )

    async def process_full(
        self,
        segments: List[dict],
        skills_context: str = "",
        mode: ProcessingMode = ProcessingMode.HYBRID,
        generate_summary: bool = False,
    ) -> ProcessingResult:
        """
        完整处理转录文本
        
        Args:
            segments: Whisper 输出的 segments 列表
            skills_context: Skills Manager 提供的上下文
            mode: 处理模式
            generate_summary: 是否生成摘要
            
        Returns:
            ProcessingResult: 包含处理结果的对象
        """
        import time
        start_time = time.time()
        
        # 调用 clean_and_diarize 进行主要处理
        diarized_transcript = await self.clean_and_diarize(
            segments=segments,
            skills_context=skills_context,
            mode=mode,
        )
        
        # 构建 cleaned_text（所有对话的文本合并）
        cleaned_text = "\n".join([
            f"[{turn.start_time}] {turn.speaker}: {turn.text}"
            for turn in diarized_transcript.turns
        ])
        
        # 计算 token 使用量（估算）
        tokens_used = self._count_tokens(cleaned_text)
        
        # 生成摘要（如果需要且是混合模式）
        insights = None
        if generate_summary and mode == ProcessingMode.HYBRID:
            # TODO: 实现摘要生成逻辑
            pass
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        return ProcessingResult(
            diarized_transcript=diarized_transcript,
            insights=insights,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used,
            mode=mode,
            cleaned_text=cleaned_text,
        )
