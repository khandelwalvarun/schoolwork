"""All ORM models — imported here so Alembic autogenerate sees them."""

from .attachments import Attachment
from .channel_config import ChannelConfig
from .children import Child
from .events import Event
from .item_comments import ItemComment
from .llm_analysis import LLMAnalysis
from .llm_calls import LLMCall
from .mcp_tool_calls import MCPToolCall
from .kid_event import KidEvent
from .library_file import LibraryFile
from .mindspark import MindsparkSession, MindsparkTopicProgress
from .notes import ParentNote
from .notification_snooze import NotificationSnooze
from .notifications import Notification
from .pattern_state import PatternState
from .practice import PracticeClassworkScan, PracticeIteration, PracticeSession
from .status_history import AssignmentStatusHistory
from .summaries import Summary
from .syllabus_overrides import SyllabusCycleOverride, SyllabusTopicStatus
from .sync_runs import SyncRun
from .topic_state import TopicState
from .translation_cache import TranslationCache
from .veracross_items import VeracrossItem

__all__ = [
    "AssignmentStatusHistory",
    "Attachment",
    "ChannelConfig",
    "Child",
    "Event",
    "ItemComment",
    "KidEvent",
    "LLMAnalysis",
    "LLMCall",
    "LibraryFile",
    "MCPToolCall",
    "MindsparkSession",
    "MindsparkTopicProgress",
    "Notification",
    "NotificationSnooze",
    "ParentNote",
    "PatternState",
    "PracticeClassworkScan",
    "PracticeIteration",
    "PracticeSession",
    "Summary",
    "SyllabusCycleOverride",
    "SyllabusTopicStatus",
    "SyncRun",
    "TopicState",
    "TranslationCache",
    "VeracrossItem",
]
