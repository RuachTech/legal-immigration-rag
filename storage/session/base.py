"""Abstract base class for session store implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Literal, Optional


@dataclass
class Citation:
    """A citation to a source document."""
    source: str
    section: str
    url: str
    excerpt: str


@dataclass
class Rationale:
    """Explanation for why a chunk is relevant."""
    chunk_id: str
    explanation: str
    confidence: float


@dataclass
class Message:
    """A single message in a conversation."""
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: List[Citation]
    rationales: List[Rationale]
    timestamp: datetime


@dataclass
class Conversation:
    """A conversation session with message history."""
    session_id: str
    user_id: Optional[str]
    messages: List[Message]
    created_at: datetime
    last_active: datetime


class SessionStore(ABC):
    """Abstract interface for session storage operations.
    
    This interface allows swapping between different session storage
    implementations (Redis, MongoDB, etc.) without changing
    application code.
    """
    
    @abstractmethod
    def create_session(self) -> str:
        """Create a new session and return session_id.
        
        Returns:
            Unique session identifier
        """
        pass
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Conversation]:
        """Retrieve session by ID.
        
        Args:
            session_id: The session identifier
            
        Returns:
            Conversation object if found, None otherwise
        """
        pass
    
    @abstractmethod
    def save_message(self, session_id: str, message: Message) -> None:
        """Add message to session.
        
        Args:
            session_id: The session identifier
            message: Message to add to the session
        """
        pass
    
    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """Remove session.
        
        Args:
            session_id: The session identifier to delete
        """
        pass
