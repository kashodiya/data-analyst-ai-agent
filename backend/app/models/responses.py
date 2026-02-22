"""Response models for API endpoints."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    """Response containing session information."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(0, description="Number of messages in the session")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """Response containing message information."""

    id: str
    role: str
    content: str
    timestamp: datetime
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    approach_explanation: Optional[str] = None
    sql_explanation: Optional[str] = None
    visualizations: Optional[List[Dict[str, Any]]] = None


class SessionListResponse(BaseModel):
    """Response containing list of sessions."""

    sessions: List[SessionResponse]
    total: int


class DatabaseSchemaResponse(BaseModel):
    """Response containing database schema information."""

    tables: List[Dict[str, Any]]
    connection_status: str
    database_type: str


class StreamChunk(BaseModel):
    """Chunk of data for streaming responses."""

    type: str = Field(..., description="Type of chunk (text, tool_call, approach, sql_explanation, visualization, done)")
    content: Optional[str] = Field(None, description="Content of the chunk")
    tool_call: Optional[Dict[str, Any]] = Field(None, description="Tool call information")
    visualization: Optional[Dict[str, Any]] = Field(None, description="Visualization configuration")
    metadata: Dict[str, Any] = Field(default_factory=dict)