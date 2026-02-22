"""Session management service using SQLite."""

import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from ..models.session import Session, Message, ToolCall
from ..config import settings


class SessionManager:
    """Manages session persistence using SQLite."""

    def __init__(self, database_path: Optional[str] = None):
        """Initialize the session manager."""
        self.database_path = database_path or settings.database_path
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """Ensure the database directory exists."""
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def get_db(self):
        """Get a database connection."""
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_db() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    timestamp TEXT NOT NULL,
                    approach_explanation TEXT,
                    sql_explanation TEXT,
                    visualizations TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages (session_id)
            """)

            await db.commit()

    async def create_session(self, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Session:
        """Create a new session."""
        session = Session(
            title=title or "New Session",
            metadata=metadata or {}
        )

        async with self.get_db() as db:
            await db.execute("""
                INSERT INTO sessions (id, title, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session.id,
                session.title,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.metadata)
            ))
            await db.commit()

        return session

    async def get_session(self, session_id: str, include_messages: bool = True) -> Optional[Session]:
        """Get a session by ID."""
        async with self.get_db() as db:
            cursor = await db.execute("""
                SELECT * FROM sessions WHERE id = ?
            """, (session_id,))
            row = await cursor.fetchone()

            if not row:
                return None

            session = Session(
                id=row['id'],
                title=row['title'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                metadata=json.loads(row['metadata'] or '{}')
            )

            if include_messages:
                cursor = await db.execute("""
                    SELECT * FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (session_id,))
                rows = await cursor.fetchall()

                for row in rows:
                    tool_calls = []
                    if row['tool_calls']:
                        tool_calls_data = json.loads(row['tool_calls'])
                        tool_calls = [ToolCall(**tc) for tc in tool_calls_data]

                    visualizations = []
                    if row.get('visualizations'):
                        visualizations = json.loads(row['visualizations'])

                    message = Message(
                        id=row['id'],
                        session_id=row['session_id'],
                        role=row['role'],
                        content=row['content'],
                        tool_calls=tool_calls,
                        timestamp=datetime.fromisoformat(row['timestamp']),
                        approach_explanation=row['approach_explanation'],
                        sql_explanation=row['sql_explanation'],
                        visualizations=visualizations
                    )
                    session.messages.append(message)

            return session

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        """List all sessions."""
        sessions = []

        async with self.get_db() as db:
            cursor = await db.execute("""
                SELECT s.*, COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.id = m.session_id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = await cursor.fetchall()

            for row in rows:
                session = Session(
                    id=row['id'],
                    title=row['title'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    metadata=json.loads(row['metadata'] or '{}')
                )
                sessions.append(session)

        return sessions

    async def add_message(self, session_id: str, message: Message) -> Message:
        """Add a message to a session."""
        async with self.get_db() as db:
            # Serialize tool calls
            tool_calls_json = None
            if message.tool_calls:
                tool_calls_json = json.dumps([tc.model_dump() for tc in message.tool_calls])

            # Serialize visualizations
            visualizations_json = None
            if message.visualizations:
                visualizations_json = json.dumps(message.visualizations)

            # Check if visualizations column exists (for backward compatibility)
            cursor = await db.execute("PRAGMA table_info(messages)")
            columns = await cursor.fetchall()
            has_viz_column = any(col[1] == 'visualizations' for col in columns)

            if has_viz_column:
                await db.execute("""
                    INSERT INTO messages (
                        id, session_id, role, content, tool_calls,
                        timestamp, approach_explanation, sql_explanation, visualizations
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.id,
                    session_id,
                    message.role,
                    message.content,
                    tool_calls_json,
                    message.timestamp.isoformat(),
                    message.approach_explanation,
                    message.sql_explanation,
                    visualizations_json
                ))
            else:
                # Add the column if it doesn't exist
                await db.execute("ALTER TABLE messages ADD COLUMN visualizations TEXT")
                await db.execute("""
                    INSERT INTO messages (
                        id, session_id, role, content, tool_calls,
                        timestamp, approach_explanation, sql_explanation, visualizations
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.id,
                    session_id,
                    message.role,
                    message.content,
                    tool_calls_json,
                    message.timestamp.isoformat(),
                    message.approach_explanation,
                    message.sql_explanation,
                    visualizations_json
                ))

            # Update session's updated_at
            await db.execute("""
                UPDATE sessions
                SET updated_at = ?, title = CASE
                    WHEN (SELECT COUNT(*) FROM messages WHERE session_id = ?) = 1
                    THEN SUBSTR(?, 1, 50)
                    ELSE title
                END
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), session_id, message.content, session_id))

            await db.commit()

        return message

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        async with self.get_db() as db:
            cursor = await db.execute("""
                DELETE FROM sessions WHERE id = ?
            """, (session_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """Update session title."""
        async with self.get_db() as db:
            cursor = await db.execute("""
                UPDATE sessions SET title = ?, updated_at = ?
                WHERE id = ?
            """, (title, datetime.utcnow().isoformat(), session_id))
            await db.commit()
            return cursor.rowcount > 0