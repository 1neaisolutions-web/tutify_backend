"""
Chatbot domain enumerations.
"""
import enum


class ChatbotCategory(str, enum.Enum):
    """Chatbot category enumeration."""

    FREE = "free"
    LLM = "llm"
    SUBJECT = "subject"


class AccessLevel(str, enum.Enum):
    """Chatbot access level enumeration."""

    FREE = "free"
    PREMIUM = "premium"


class CapabilityCategory(str, enum.Enum):
    """Capability category enumeration."""

    ANALYSIS = "analysis"
    INSTRUCTION = "instruction"
    FEEDBACK = "feedback"
    TRACKING = "tracking"


class ProcessingMode(str, enum.Enum):
    """Processing mode enumeration."""

    CHAT = "chat"
    STRUCTURED = "structured"
    STREAMING = "streaming"
    BATCH = "batch"


class MessageRole(str, enum.Enum):
    """Message role enumeration."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
