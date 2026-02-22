"""Request models for API endpoints."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    title: Optional[str] = Field(None, description="Optional title for the session")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class SendMessageRequest(BaseModel):
    """Request to send a message in a session."""

    content: str = Field(..., description="Content of the message")
    include_approach: bool = Field(True, description="Whether to include approach explanation")
    include_sql_explanation: bool = Field(True, description="Whether to include SQL explanation")


class DatabaseConnectionRequest(BaseModel):
    """Request to configure database connection."""

    connection_string: str = Field(..., description="Database connection string")
    database_type: str = Field("sqlite", description="Type of database (sqlite, postgres, mysql)")
    schema_name: Optional[str] = Field(None, description="Schema name for databases that support schemas")