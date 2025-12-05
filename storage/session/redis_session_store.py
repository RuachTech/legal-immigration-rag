"""RedisSessionStore: Implements SessionStore interface using Redis backend."""

import json
import uuid
from datetime import datetime
from typing import Any

import redis

from storage.session.base import Citation, Conversation, Message, Rationale, SessionStore


class RedisSessionStore(SessionStore):
    """Redis implementation of SessionStore interface.
    
    Stores conversation sessions with TTL in Redis.
    Uses dependency injection for Redis client.
    """
    
    def __init__(
        self,
        client: "redis.Redis[Any]",  # type: ignore[type-arg]
        ttl_seconds: int = 86400
    ) -> None:
        """Initialize Redis session store with injected client.
        
        Args:
            client: Redis client instance (injected, with decode_responses=True)
            ttl_seconds: Time-to-live for sessions in seconds (default: 24 hours)
        """
        self._client = client
        self._ttl_seconds = ttl_seconds

    def create_session(self) -> str:
        """Create a new session with unique ID.
        
        Returns:
            Unique session identifier (UUID4)
        """
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        conversation_dict: dict[str, Any] = {
            "session_id": session_id,
            "user_id": None,
            "messages": [],
            "created_at": now,
            "last_active": now
        }
        
        self._client.setex(
            f"session:{session_id}",
            self._ttl_seconds,
            json.dumps(conversation_dict)
        )
        return session_id

    def get_session(self, session_id: str) -> Conversation:
        """Retrieve a conversation session by ID.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Conversation object with full message history
            
        Raises:
            KeyError: If session not found
        """
        data = self._client.get(f"session:{session_id}")
        if not data:
            raise KeyError(f"Session {session_id} not found")
        
        conv_dict: dict[str, Any] = json.loads(str(data))
        
        # Deserialize messages with nested objects
        messages: list[Message] = []
        for msg_dict in conv_dict["messages"]:
            citations = [
                Citation(**cit) for cit in msg_dict.get("citations", [])
            ]
            rationales = [
                Rationale(**rat) for rat in msg_dict.get("rationales", [])
            ]
            message = Message(
                id=msg_dict["id"],
                role=msg_dict["role"],
                content=msg_dict["content"],
                citations=citations,
                rationales=rationales,
                timestamp=datetime.fromisoformat(msg_dict["timestamp"])
            )
            messages.append(message)
        
        return Conversation(
            session_id=conv_dict["session_id"],
            user_id=conv_dict.get("user_id"),
            messages=messages,
            created_at=datetime.fromisoformat(conv_dict["created_at"]),
            last_active=datetime.fromisoformat(conv_dict["last_active"])
        )

    def save_message(self, session_id: str, message: Message) -> None:
        """Add a message to an existing session.
        
        Args:
            session_id: Unique session identifier
            message: Message object to persist
            
        Raises:
            KeyError: If session not found
        """
        data = self._client.get(f"session:{session_id}")
        if not data:
            raise KeyError(f"Session {session_id} not found")
        
        conv_dict: dict[str, Any] = json.loads(str(data))
        
        # Serialize message with nested objects
        message_dict: dict[str, Any] = {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "citations": [
                {"source": c.source, "section": c.section, "url": c.url, "excerpt": c.excerpt}
                for c in message.citations
            ],
            "rationales": [
                {"chunk_id": r.chunk_id, "explanation": r.explanation, "confidence": r.confidence}
                for r in message.rationales
            ],
            "timestamp": message.timestamp.isoformat()
        }
        
        conv_dict["messages"].append(message_dict)
        conv_dict["last_active"] = datetime.utcnow().isoformat()
        
        self._client.setex(
            f"session:{session_id}",
            self._ttl_seconds,
            json.dumps(conv_dict)
        )

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all associated messages.
        
        Args:
            session_id: Unique session identifier to delete
        """
        self._client.delete(f"session:{session_id}")
